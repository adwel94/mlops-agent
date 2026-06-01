"""Generate a VLA-style dataset from ManiSkill demonstrations.

Two interfaces:
  - Python:  from scripts.generate import run; run(task="PickCube-v1", count=100)
  - CLI:     python scripts/generate.py --task PickCube-v1 --count 100

Mechanism: replays the official Hugging Face demos (downloaded once via
download_demo) with the requested observation/control mode and writes a new
HDF5. Forces render_backend='cpu' on Windows so the CUDA-Vulkan interop
segfault in the default GPU render path is avoided.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import gymnasium as gym

_orig_make = gym.make
def _patched_make(env_id, *args, **kwargs):
    kwargs.setdefault("render_backend", "cpu")
    return _orig_make(env_id, *args, **kwargs)
gym.make = _patched_make

from mani_skill.trajectory import replay_trajectory as _rt  # noqa: E402


# Demos (input) live in ManiSkill's external cache — reproducible via /setup.
DEMOS_ROOT = Path.home() / ".maniskill" / "demos"
# Generated datasets (output) stay INSIDE the project so the harness is
# self-contained: <project>/data/datasets/<task>/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASETS_ROOT = PROJECT_ROOT / "data" / "datasets"


def default_traj_path(task: str) -> Path:
    return DEMOS_ROOT / task / "motionplanning" / "trajectory.h5"


def _resolve_control_mode(traj_path: Path, target_control_mode: str | None) -> str:
    if target_control_mode:
        return target_control_mode
    with open(traj_path.with_suffix(".json")) as f:
        meta = json.load(f)
    return meta["env_info"]["env_kwargs"].get("control_mode", "pd_joint_pos")


def run(
    task: str = "PickCube-v1",
    count: int = 100,
    obs_mode: str = "rgb",
    sim_backend: str = "physx_cpu",
    num_envs: int = 1,
    target_control_mode: str | None = None,
    traj_path: str | Path | None = None,
    save_traj: bool = True,
    save_video: bool = False,
    verbose: bool = False,
) -> Path:
    """Generate `count` episodes by replaying official demos.

    Returns the path to the produced HDF5 file.
    """
    src = Path(traj_path) if traj_path else default_traj_path(task)
    if not src.exists():
        raise FileNotFoundError(
            f"Source trajectory not found: {src}\n"
            f"Run `python -m mani_skill.utils.download_demo {task}` first."
        )

    argv = [
        "generate.py",
        "--traj-path", str(src),
        "--sim-backend", sim_backend,
        "--obs-mode", obs_mode,
        "--count", str(count),
        "--num-envs", str(num_envs),
    ]
    if save_traj:
        argv.append("--save-traj")
    if save_video:
        argv.append("--save-video")
    if verbose:
        argv.append("--verbose")
    if target_control_mode:
        argv += ["--target-control-mode", target_control_mode]

    old_argv = sys.argv
    sys.argv = argv
    try:
        _rt.main(_rt.parse_args())
    finally:
        sys.argv = old_argv

    # replay_trajectory writes next to the source demo (external cache).
    # Move the produced .h5 (+ its .json) into the project's data/ dir so all
    # generated artifacts stay self-contained.
    final_ctrl = _resolve_control_mode(src, target_control_mode)
    produced = src.parent / f"trajectory.{obs_mode}.{final_ctrl}.{sim_backend}.h5"
    if not save_traj:
        return produced  # nothing was written to disk

    dest_dir = DATASETS_ROOT / task
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / produced.name
    shutil.move(str(produced), str(dest))
    produced_json = produced.with_suffix(".json")
    if produced_json.exists():
        shutil.move(str(produced_json), str(dest.with_suffix(".json")))
    return dest


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--task", default="PickCube-v1")
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--obs-mode", default="rgb")
    p.add_argument("--sim-backend", default="physx_cpu")
    p.add_argument("--num-envs", type=int, default=1)
    p.add_argument("--target-control-mode", default=None)
    p.add_argument("--traj-path", default=None)
    p.add_argument("--no-save-traj", action="store_true",
                   help="Skip writing the output HDF5")
    p.add_argument("--save-video", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    out = run(
        task=args.task,
        count=args.count,
        obs_mode=args.obs_mode,
        sim_backend=args.sim_backend,
        num_envs=args.num_envs,
        target_control_mode=args.target_control_mode,
        traj_path=args.traj_path,
        save_traj=not args.no_save_traj,
        save_video=args.save_video,
        verbose=args.verbose,
    )
    print(f"\nGenerated dataset -> {out}")


if __name__ == "__main__":
    _cli()
