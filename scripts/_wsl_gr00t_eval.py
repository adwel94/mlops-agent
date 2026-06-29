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


def _cube_states(base, lift_thresh):
    """Per-cube (grasped, z, grasped_and_lifted) read straight from env internals.

    Diagnostic-only and best-effort: returns [] when the env doesn't expose a
    `cubes` list (e.g. builtin tasks) so the rollout stays task-agnostic. For the
    colored-cube tasks the cube order matches label_metadata's color list, so the
    caller maps index -> color without importing the env.
    """
    cubes = getattr(base, "cubes", None)
    if not cubes:
        return []
    out = []
    for c in cubes:
        g = bool(np.asarray(np1(base.agent.is_grasping(c))).reshape(-1)[0])
        z = float(np1(c.pose.p)[2])
        out.append((g, z, g and z > lift_thresh))
    return out


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
    p.add_argument("--log-jsonl", default=None)        # per-episode diagnostic records
    args = p.parse_args()

    sidecar = json.load(open(args.traj_path.replace(".h5", ".json")))
    eps_meta = sidecar.get("episodes", [])
    env_id = sidecar.get("env_info", {}).get("env_id", args.task)
    label_md = sidecar.get("label_metadata") or {}
    colors = label_md.get("target_id")                 # ["red","green","blue"] or None

    client = PolicyClient(args.server_host, args.server_port)
    client.ping()   # fail fast if the server is unreachable

    env, base, solver, base_p, base_q = make_env_and_solver(
        args.task, sim_backend=args.sim_backend, obs_mode="rgb",
    )
    # success = grasped AND lifted clear of table; mirror the env's own threshold
    # (cube_half_size + 0.04) so the any-cube probe matches evaluate()'s logic.
    lift_thresh = float(getattr(base, "cube_half_size", 0.02)) + 0.04
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
    n_anypick = n_picked_tgt = 0     # diagnostic: manipulation vs color-grounding
    records = []
    pbar = tqdm(keys)
    for k in keys:
        i = int(k.split("_")[1])
        ep = f[k]
        orig_succ += bool(np.asarray(ep["success"])[-1])
        instr = _instruction(ep, label_md, args.instruction, env_id)
        seed = eps_meta[i].get("episode_seed", i) if i < len(eps_meta) else i
        budget = args.max_steps or int(ep["actions"].shape[0])

        obs, _ = env.reset(seed=seed)
        # env target after the seeded reset (cross-check vs the recorded label)
        tgt = None
        if hasattr(base, "target_id"):
            try:
                tgt = int(np.asarray(np1(base.target_id)).reshape(-1)[0])
            except Exception:
                tgt = None
        ncubes = len(_cube_states(base, lift_thresh))
        ever_gl = [False] * ncubes              # cube j ever grasped+lifted this episode
        max_z = [-1e9] * ncubes                 # cube j peak height
        last_q = np1(base.agent.robot.get_qpos())
        success = False
        ep_ik_fails = 0
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
                ep_ik_fails += int(failed)
                obs, _r, _term, _trunc, info = env.step(
                    np.hstack([arm, float(grip[h, 0])]))
                last_q = np1(base.agent.robot.get_qpos())
                success = bool(np.asarray(info["success"]).reshape(-1)[0])
                for j, (_g, z, gl) in enumerate(_cube_states(base, lift_thresh)):
                    ever_gl[j] = ever_gl[j] or gl
                    max_z[j] = max(max_z[j], z)
                t += 1
        pol_succ += int(success)
        ik_fail_total += ep_ik_fails

        # diagnostic rollup: did it pick up ANY cube, and was it the RIGHT color?
        any_pick = bool(any(ever_gl)) if ever_gl else None
        picked_target = (bool(ever_gl[tgt]) if (ever_gl and tgt is not None
                                                and tgt < len(ever_gl)) else None)
        picked_colors = ([colors[j] for j in range(len(ever_gl)) if ever_gl[j]]
                         if (colors and ever_gl) else [])
        if any_pick:
            n_anypick += 1
        if picked_target:
            n_picked_tgt += 1
        # final tcp -> target-cube distance + MISS VECTOR (precision signal), best-effort.
        # 벡터(tcp-target)를 남겨야 "한쪽으로 일정한 편향(프레임 버그)" vs "랜덤 산포(진짜
        # 부정확)" 를 사후 분석 가능. (스칼라 거리만으론 방향을 못 봄.)
        final_dist = miss_vec = None
        try:
            extra = obs["extra"]
            tcp_p = _b0(extra["tcp_pose"]).astype(float)[:3]
            tgt_p = _b0(extra["target_pose"]).astype(float)[:3]
            miss_vec = (tcp_p - tgt_p)
            final_dist = float(np.linalg.norm(miss_vec))
            miss_vec = [round(float(v), 4) for v in miss_vec]
        except Exception:
            pass
        records.append({
            "episode": i, "seed": int(seed),
            "target_id": tgt,
            "target_color": (colors[tgt] if (colors and tgt is not None
                                             and tgt < len(colors)) else None),
            "instruction": instr,
            "budget": int(budget), "steps_used": int(t),
            "success": bool(success), "ik_fails": int(ep_ik_fails),
            "any_pick": any_pick, "picked_target": picked_target,
            "picked_colors": picked_colors,
            "max_lift": ({colors[j]: round(max_z[j], 4) for j in range(len(ever_gl))}
                         if (colors and ever_gl) else {}),
            "final_tcp_to_target_m": (round(final_dist, 4)
                                      if final_dist is not None else None),
            "miss_vec": miss_vec,   # [dx,dy,dz] = tcp-target; 편향 vs 산포 사후분석용
        })
        pbar.update(1)
        pbar.set_postfix(dict(orig=orig_succ, pol=pol_succ, anypick=n_anypick))

    f.close()
    env.close()
    client.close()
    n = len(keys)

    if args.log_jsonl:
        with open(args.log_jsonl, "w") as lf:
            for r in records:
                lf.write(json.dumps(r) + "\n")
        print(f"[gr00t_eval] per-episode diagnostics -> {args.log_jsonl}")

    # color-grounding readout: of episodes where SOME cube was picked, how often
    # was it the target color? (random color choice over k cubes -> ~1/k)
    color_rate = n_picked_tgt / max(n_anypick, 1)
    print(f"DONE gr00t_eval episodes={n} orig_success={orig_succ}/{n} "
          f"policy_success={pol_succ}/{n} success_rate={pol_succ / max(n, 1):.3f} "
          f"ik_fails={ik_fail_total} any_pick={n_anypick}/{n} "
          f"picked_target={n_picked_tgt}/{n} correct_color_rate={color_rate:.3f}")


if __name__ == "__main__":
    main()
