"""WSL-side: roll out a GR00T policy in sim and measure task success rate.

The policy (GR00T, GPU) runs as a ZMQ server on a remote box (e.g. RunPod); this
process is the rollout client — it owns the sim + mplib IK and never imports torch.
Per sampled episode: reset the env to the episode's seed, then closed-loop:

    build observation (current rgb + qpos + abs-EEF + language)
      -> policy.get_action  (ZMQ -> server)            # absolute EEF target, 16-step horizon
      -> rot6d_to_quat -> world target pose -> mplib IK -> arm joints
      -> env.step (pd_joint_pos)                        # execute --action-steps, then replan
    until success or --max-steps.

Reports success rate vs the recorded episodes (a deployment metric, not a label
gate). Wire format = msgpack + msgpack_numpy, matching GR00T's PolicyServer for the
get_action path (no gr00t/torch dependency here). Invoked by scripts/gr00t_eval.py.
"""
import argparse
import json
import random
import sys

PROJECT_ROOT = "/mnt/c/Users/hun41/PycharmProjects/maniskill"
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import h5py
import msgpack
import msgpack_numpy as mnp
import zmq
from tqdm import tqdm

from scripts.ee_convert import episode_to_abs_eef, rot6d_to_quat
from scripts.ik_exec import np1, make_env_and_solver, solve_to_arm
from scripts.h5_to_lerobot import BASE_CAMERA  # single source for the camera contract


# ---- minimal GR00T PolicyClient (get_action / ping path only) ---------------

class PolicyClient:
    """ZMQ REQ client matching gr00t.policy.server_client.PolicyServer's wire format.

    Request  = msgpack({"endpoint": str, "data": {...}}, default=mnp.encode)
    Response = msgpack(result, object_hook=mnp.decode)  # get_action -> [action, info]
    The ModalityConfig custom hook only fires on get_modality_config, so plain
    msgpack_numpy is wire-compatible for get_action/ping.
    """

    def __init__(self, host, port, timeout_ms=120000):
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.REQ)
        self.sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.sock.setsockopt(zmq.LINGER, 0)
        self.sock.connect(f"tcp://{host}:{port}")

    def _call(self, endpoint, data=None):
        req = {"endpoint": endpoint}
        if data is not None:
            req["data"] = data
        self.sock.send(msgpack.packb(req, default=mnp.encode))
        rep = msgpack.unpackb(self.sock.recv(), object_hook=mnp.decode, raw=False)
        if isinstance(rep, dict) and "error" in rep:
            raise RuntimeError(f"policy server error: {rep['error']}")
        return rep

    def ping(self):
        return self._call("ping")

    def get_action(self, observation, options=None):
        action, _info = self._call(
            "get_action", {"observation": observation, "options": options or {}})
        return action

    def close(self):
        self.sock.close()
        self.ctx.term()


def _b0(x):
    """Strip the env batch dim (num_envs=1) -> numpy."""
    a = x.cpu().numpy() if hasattr(x, "cpu") else np.asarray(x)
    return a[0]


def _instruction(ep, label_md, template, fallback):
    """Same per-episode language string h5_to_lerobot trained on (decoded labels)."""
    decoded = {}
    extra = ep["obs"].get("extra", {})
    for k_lab, names in label_md.items():
        try:
            decoded[k_lab] = names[int(np.asarray(extra[k_lab])[0])]
        except Exception:
            pass
    if template:
        try:
            return template.format(**decoded)
        except Exception:
            pass
    if decoded:
        return ", ".join(str(v) for v in decoded.values())
    return fallback


def _build_obs(obs, cam, instr):
    """sim obs -> GR00T observation dict (batch=1, time=1)."""
    rgb = _b0(obs["sensor_data"][cam]["rgb"]).astype(np.uint8)     # (H,W,3)
    qpos = _b0(obs["agent"]["qpos"]).astype(np.float32)            # (Q,)
    tcp = _b0(obs["extra"]["tcp_pose"]).astype(np.float64)         # (7,)
    eef = episode_to_abs_eef(tcp[None])[0].astype(np.float32)      # (9,)
    return {
        "video": {cam: rgb[None, None]},                           # (1,1,H,W,3) uint8
        "state": {"qpos": qpos[None, None], "eef": eef[None, None]},  # (1,1,*)
        # 언어 키는 모달리티 설정(new_embodiment_config.py)의 language modality_keys 와
        # 일치해야 함 = "annotation.human.task_description" (학습 때 쓴 키). shape (B,1).
        "language": {"annotation.human.task_description": [[instr]]},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--traj-path", required=True)   # source image dataset h5 (seeds + labels)
    p.add_argument("--server-host", required=True)
    p.add_argument("--server-port", type=int, default=5555)
    p.add_argument("--count", type=int, default=10)   # 0 = all; else random sample
    p.add_argument("--seed", type=int, default=0)     # reproducible random sample
    p.add_argument("--max-steps", type=int, default=0)   # 0 = recorded episode length
    p.add_argument("--action-steps", type=int, default=16)  # executed per replan (<= horizon)
    p.add_argument("--instruction", default=None)     # template over label_metadata keys
    p.add_argument("--sim-backend", default="cpu")
    args = p.parse_args()

    sidecar = json.load(open(args.traj_path.replace(".h5", ".json")))
    eps_meta = sidecar.get("episodes", [])
    env_id = sidecar.get("env_info", {}).get("env_id", args.task)
    label_md = sidecar.get("label_metadata") or {}

    client = PolicyClient(args.server_host, args.server_port)
    client.ping()   # fail fast if the server is unreachable

    env, base, solver, base_p, base_q = make_env_and_solver(
        args.task, sim_backend=args.sim_backend, obs_mode="rgb",
    )
    obs0, _ = env.reset(seed=0)
    # select the policy's camera by NAME (the embodiment contract), not by position.
    # must match what h5_to_lerobot fed the model (observation.images.<BASE_CAMERA>).
    available = list(obs0["sensor_data"].keys())
    if BASE_CAMERA not in available:
        raise SystemExit(
            f"camera {BASE_CAMERA!r} not found in env sensors {available}. "
            f"The trained model expects {BASE_CAMERA!r}; make the env's primary "
            f"camera {BASE_CAMERA!r} (see new_embodiment_config)."
        )
    cam = BASE_CAMERA

    f = h5py.File(args.traj_path, "r")
    keys = sorted(f.keys(), key=lambda k: int(k.split("_")[1]))
    if args.count and args.count < len(keys):
        keys = sorted(random.Random(args.seed).sample(keys, args.count),
                      key=lambda k: int(k.split("_")[1]))

    orig_succ = pol_succ = ik_fail_total = 0
    pbar = tqdm(keys)
    for k in keys:
        i = int(k.split("_")[1])
        ep = f[k]
        orig_succ += bool(np.asarray(ep["success"])[-1])
        instr = _instruction(ep, label_md, args.instruction, env_id)
        seed = eps_meta[i].get("episode_seed", i) if i < len(eps_meta) else i
        budget = args.max_steps or int(ep["actions"].shape[0])

        obs, _ = env.reset(seed=seed)
        last_q = np1(base.agent.robot.get_qpos())
        success = False
        t = 0
        while t < budget and not success:
            action = client.get_action(_build_obs(obs, cam, instr))
            eef = np.asarray(action["eef"])[0]          # (H,9) absolute xyz+rot6d
            grip = np.asarray(action["gripper"])[0]     # (H,1)
            horizon = min(args.action_steps, eef.shape[0])
            for h in range(horizon):
                if t >= budget or success:
                    break
                tp = eef[h, :3].astype(float)
                tq = rot6d_to_quat(eef[h, 3:9].astype(float))
                arm, failed = solve_to_arm(solver, tp, tq, base_p, base_q, last_q)
                ik_fail_total += int(failed)
                obs, _r, _term, _trunc, info = env.step(
                    np.hstack([arm, float(grip[h, 0])]))
                last_q = np1(base.agent.robot.get_qpos())
                success = bool(np.asarray(info["success"]).reshape(-1)[0])
                t += 1
        pol_succ += int(success)
        pbar.update(1)
        pbar.set_postfix(dict(orig=orig_succ, pol=pol_succ))

    f.close()
    env.close()
    client.close()
    n = len(keys)
    print(f"DONE gr00t_eval episodes={n} orig_success={orig_succ}/{n} "
          f"policy_success={pol_succ}/{n} success_rate={pol_succ / max(n, 1):.3f} "
          f"ik_fails={ik_fail_total}")


if __name__ == "__main__":
    main()
