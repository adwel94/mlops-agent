"""Executor: verify that 7d EE-delta actions reproduce task success via per-step IK.

For each episode in a (joint) dataset h5: reset the env to the episode's seed,
convert its recorded joint trajectory to 7d EE-delta (scripts.ee_convert), then
execute those deltas open-loop through per-step IK — each step the EE-delta
is applied to the recorded CURRENT tcp pose, solved to joints via solve_to_arm, and
stepped with pd_joint_pos. Reports how often success still reproduces vs the
trajectory's recorded success.

This is the Path-B method gate. Runs inside WSL on Windows (mplib + llvmpipe
Vulkan), natively on macOS/Linux (scripts.ik_exec 이 IK 백엔드를 가용성으로 선택).
Invoked by scripts/ee_verify.py. IK plumbing is shared with the GR00T policy
rollout via scripts/ik_exec.py.
"""
import argparse
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import h5py
from tqdm import tqdm

from scripts.ee_convert import episode_joint_to_ee, ee_delta_to_target_pose
from scripts.ik_exec import np1, make_env_and_solver, solve_to_arm


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--traj-path", required=True)   # WSL path to the dataset h5 (has obs/extra/tcp_pose)
    p.add_argument("--count", type=int, default=0)  # 0 = all; else random sample of this many
    p.add_argument("--seed", type=int, default=0)   # reproducible random sample
    p.add_argument("--sim-backend", default="cpu")
    args = p.parse_args()

    sidecar = json.load(open(args.traj_path.replace(".h5", ".json")))
    eps_meta = sidecar.get("episodes", [])
    robot_uids = sidecar.get("env_info", {}).get("robot_uids", "panda")

    env, base, solver, base_p, base_q = make_env_and_solver(
        args.task, sim_backend=args.sim_backend, obs_mode="none", robot_uids=robot_uids,
    )

    f = h5py.File(args.traj_path, "r")
    keys = sorted(f.keys(), key=lambda k: int(k.split("_")[1]))
    if args.count and args.count < len(keys):
        # random sample (method gate): representative subset, reproducible via --seed
        keys = sorted(random.Random(args.seed).sample(keys, args.count),
                      key=lambda k: int(k.split("_")[1]))

    orig_succ = ee_succ = ik_fail_total = 0
    pbar = tqdm(keys)
    for k in keys:
        i = int(k.split("_")[1])
        ep = f[k]
        tcp = ep["obs"]["extra"]["tcp_pose"][:]
        act = ep["actions"][:]
        ee = episode_joint_to_ee(tcp, act)
        orig = bool(np.asarray(ep["success"])[-1])
        orig_succ += orig
        seed = eps_meta[i].get("episode_seed", i) if i < len(eps_meta) else i

        env.reset(seed=seed)
        last_q = np1(base.agent.robot.get_qpos())
        success = False
        ik_fail = 0
        for t in range(ee.shape[0]):
            # Apply each delta to the RECORDED tcp pose it was computed from (so the
            # target is the recorded next waypoint). This validates the EE labels +
            # IK fidelity without the open-loop drift a closed-loop policy would
            # correct. (Using the sim's drifting current pose instead under-tracks.)
            p_t = tcp[t, :3].astype(float)
            q_t = tcp[t, 3:].astype(float)
            tp, tq = ee_delta_to_target_pose(p_t, q_t, ee[t])   # world-frame target
            arm, failed = solve_to_arm(solver, tp, tq, base_p, base_q, last_q)
            ik_fail += int(failed)
            action = np.hstack([arm, float(ee[t][6])])
            _obs, _r, _term, _trunc, info = env.step(action)
            last_q = np1(base.agent.robot.get_qpos())
            success = bool(np.asarray(info["success"]).reshape(-1)[0])
        ee_succ += int(success)
        ik_fail_total += ik_fail
        pbar.update(1)
        pbar.set_postfix(dict(orig=orig_succ, ee=ee_succ))

    f.close()
    env.close()
    n = len(keys)
    rate = ee_succ / max(orig_succ, 1)
    print(f"DONE ee_verify orig_success={orig_succ}/{n} ee_success={ee_succ}/{n} "
          f"reproduction_rate={rate:.3f} ik_fails={ik_fail_total}")


if __name__ == "__main__":
    main()
