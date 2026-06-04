"""Turn a raw action trajectory into a dataset by replaying it with RGB images.

This is the shared consumer stage. It takes a raw trajectory produced by EITHER
producer — `fetch_sample_h5` (downloaded demo) or `task_to_h5` (motion planning)
— and replays it to record observations (camera images + state). Both producers
emit the same self-describing format (actions + env_states + a JSON sidecar), so
this step is identical regardless of source; it reads env_id/control_mode out of
the sidecar and never needs to know which producer made the file.

Task-specific metadata rides along automatically: whatever an env returns from
`_get_obs_extra` is recorded per step (e.g. ThreeColoredCubes' target_id), and if
the env defines `label_metadata()`, its integer->label decoder is written into the
output's JSON sidecar — so a new task needs NO change here.

Two interfaces:
  - Python:  from scripts.h5_add_images import run; run(task="PickCube-v1", count=100)
  - CLI:     python scripts/h5_add_images.py --task PickCube-v1 --count 100

Mechanism: replays with the requested observation/control mode and writes a new
HDF5. Forces render_backend='cpu' on Windows (the GPU render path segfaults).
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


def _ensure_custom_envs() -> None:
    """Register this project's custom tasks so replay can recreate them.

    Built-in tasks are auto-registered by replay_trajectory's own imports; custom
    ones (e.g. ThreeColoredCubes-v1, produced by task_to_h5) need
    scripts.custom_envs imported. Works whether this is imported or run as a script.
    """
    import importlib
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    importlib.import_module("scripts.custom_envs")


# All trajectories (from either producer) live INSIDE the project under
# data/datasets/<task>/ — so this consumer has no external dependency.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASETS_ROOT = PROJECT_ROOT / "data" / "datasets"


def default_traj_path(task: str) -> Path:
    """Default input: the task_to_h5 (motion-planning) output for this task.

    To consume a fetched demo instead, pass traj_path=data/datasets/<task>/trajectory.h5.
    """
    return DATASETS_ROOT / task / "motionplanning.h5"


def _resolve_control_mode(traj_path: Path, target_control_mode: str | None) -> str:
    if target_control_mode:
        return target_control_mode
    with open(traj_path.with_suffix(".json")) as f:
        meta = json.load(f)
    return meta["env_info"]["env_kwargs"].get("control_mode", "pd_joint_pos")


def _write_label_metadata(task: str, dataset_json: Path) -> None:
    """If the env exposes label_metadata(), stamp it into the dataset's sidecar.

    Generic hook: makes the integer labels in obs/extra (e.g. target_id) decodable
    from the dataset alone. Envs without the method are left untouched.
    """
    _ensure_custom_envs()  # robust if called standalone (custom task must be registered)
    try:
        env = gym.make(task, num_envs=1, obs_mode="none",
                       sim_backend="physx_cpu", render_backend="cpu")
    except Exception:
        return  # if we can't build it, just skip — metadata is best-effort
    try:
        base = env.unwrapped
        if not hasattr(base, "label_metadata"):
            return
        labels = base.label_metadata()
    finally:
        env.close()

    if not dataset_json.exists():
        return
    meta = json.loads(dataset_json.read_text())
    meta["label_metadata"] = labels
    dataset_json.write_text(json.dumps(meta, indent=2))
    print(f"[h5_add_images] recorded label_metadata -> {labels}")


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
    """Generate `count` episodes by replaying an action trajectory.

    Returns the path to the produced HDF5 dataset.
    """
    src = Path(traj_path) if traj_path else default_traj_path(task)
    if not src.exists():
        raise FileNotFoundError(
            f"Source trajectory not found: {src}\n"
            f"Produce one first: `python scripts/task_to_h5.py --task {task}` "
            f"(or `python scripts/fetch_sample_h5.py --task {task}` for a demo)."
        )

    argv = [
        "h5_add_images.py",
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

    _ensure_custom_envs()  # so replay can recreate custom tasks (e.g. task_to_h5 output)

    old_argv = sys.argv
    sys.argv = argv
    try:
        _rt.main(_rt.parse_args())
    finally:
        sys.argv = old_argv

    # replay_trajectory names its output after the SOURCE stem (not a fixed
    # "trajectory"): fetched demo `trajectory.h5` -> `trajectory.<obs>...`,
    # solved `motionplanning.h5` -> `motionplanning.<obs>...`. The stem thus
    # records which producer the actions came from.
    final_ctrl = _resolve_control_mode(src, target_control_mode)
    produced = src.parent / f"{src.stem}.{obs_mode}.{final_ctrl}.{sim_backend}.h5"
    if not save_traj:
        return produced  # nothing was written to disk

    # Move the produced .h5 (+ its .json) into the project's data/ dir so all
    # generated artifacts stay self-contained. If the source already lives there
    # (the normal case now), the file is already in place — skip the no-op move.
    dest_dir = DATASETS_ROOT / task
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / produced.name
    if produced.resolve() != dest.resolve():
        shutil.move(str(produced), str(dest))
        produced_json = produced.with_suffix(".json")
        if produced_json.exists():
            if dest.with_suffix(".json").exists():
                dest.with_suffix(".json").unlink()
            shutil.move(str(produced_json), str(dest.with_suffix(".json")))

    # stamp the env's integer-label decoder into the dataset sidecar (generic; a
    # no-op for envs that don't define label_metadata)
    _write_label_metadata(task, dest.with_suffix(".json"))
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
