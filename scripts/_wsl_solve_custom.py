"""WSL-side batch generator for CUSTOM tasks (mirrors ManiSkill's run.py loop).

Runs a custom solution (from scripts.custom_solutions) over seeds 0..N, recording
each successful episode into an HDF5 via RecordEpisode. Same record layout as the
built-in solver (<record-dir>/<task>/motionplanning/<name>.h5) so the Windows
orchestrator (solve.py) can flatten/move it identically.

Runs inside WSL (needs mplib + llvmpipe Vulkan). Invoked by scripts/task_to_h5.py.
"""
import argparse
import os.path as osp
import sys

PROJECT_ROOT = "/mnt/c/Users/hun41/PycharmProjects/maniskill"
sys.path.insert(0, PROJECT_ROOT)

# WSL has only the llvmpipe software renderer; let sapien auto-select it when the
# explicit 'cpu' device is rejected (same fix as solve's built-in wrapper).
import sapien.render as _R
_orig_rs = _R.RenderSystem
def _safe_rs(*a, **k):
    try:
        return _orig_rs(*a, **k)
    except RuntimeError:
        return _orig_rs()
_R.RenderSystem = _safe_rs

import numpy as np
import gymnasium as gym
from tqdm import tqdm

import mani_skill.envs  # noqa: F401
import scripts.custom_envs  # noqa: F401  (registers custom tasks)
from scripts.custom_solutions import SOLUTIONS
from mani_skill.utils.wrappers.record import RecordEpisode


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--record-dir", required=True)
    p.add_argument("--traj-name", default="motionplanning")
    p.add_argument("--obs-mode", default="none")
    p.add_argument("--sim-backend", default="cpu")
    p.add_argument("--only-success", action="store_true")
    args = p.parse_args()

    if args.task not in SOLUTIONS:
        raise SystemExit(f"No custom solution for {args.task}. "
                         f"Available: {list(SOLUTIONS)}")
    solve = SOLUTIONS[args.task]

    env = gym.make(
        args.task, obs_mode=args.obs_mode, control_mode="pd_joint_pos",
        render_mode="rgb_array", sim_backend=args.sim_backend,
        render_backend="cpu", reward_mode="none",
    )
    env = RecordEpisode(
        env,
        output_dir=osp.join(args.record_dir, args.task, "motionplanning"),
        trajectory_name=args.traj_name, save_video=False,
        source_type="motionplanning",
        source_desc="custom colored-cube pick solution",
        video_fps=30, record_reward=False, save_on_reset=False,
    )

    print(f"Custom motion planning on {args.task}")
    pbar = tqdm(range(args.count))
    seed, passed, failed = 0, 0, 0
    successes = []
    while passed < args.count:
        try:
            res = solve(env, seed=seed)
            success = bool(res[-1]["success"].item())
        except Exception as e:  # motion-plan failure -> skip this seed
            print(f"[seed {seed}] motion planning error: {e}")
            success, res = False, -1
            failed += 1
        successes.append(success)

        if args.only_success and not success:
            env.flush_trajectory(save=False)
            seed += 1
            continue
        env.flush_trajectory()
        passed += 1
        seed += 1
        pbar.update(1)
        pbar.set_postfix(dict(success_rate=float(np.mean(successes))))

    env.close()
    print(f"DONE success_rate={float(np.mean(successes)):.3f} "
          f"failed_plans={failed} seeds_used={seed}")


if __name__ == "__main__":
    main()
