"""Fetch (download) official ManiSkill demonstration datasets for a task.

One of two action-source ("producer") skills. `fetch` pulls ready-made official
demos from Hugging Face — the fast/baseline path. The other producer, `solve`,
generates actions from scratch via motion planning in WSL. Both yield the same
raw trajectory format (actions + env_states, no images), which `generate` then
replays to add RGB observations.

Idempotent: if demos already exist for the task, skips re-download unless
--force is passed.

Two interfaces:
  - Python:  from scripts.fetch import run; run(task="PickCube-v1")
  - CLI:     python scripts/fetch.py --task PickCube-v1
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


DEMOS_ROOT = Path.home() / ".maniskill" / "demos"


def task_demo_dir(task: str) -> Path:
    return DEMOS_ROOT / task


def is_downloaded(task: str) -> bool:
    """A task is considered downloaded if its motionplanning trajectory.h5 exists."""
    return (task_demo_dir(task) / "motionplanning" / "trajectory.h5").exists()


def run(task: str = "PickCube-v1", force: bool = False) -> Path:
    """Ensure demos for `task` are downloaded. Returns the task's demo directory.

    If already present and not `force`, returns immediately without re-downloading.
    """
    target = task_demo_dir(task)

    if is_downloaded(task) and not force:
        print(f"[fetch] {task}: already present -> {target}")
        return target

    print(f"[fetch] {task}: downloading demos via mani_skill.utils.download_demo ...")
    subprocess.run(
        [sys.executable, "-m", "mani_skill.utils.download_demo", task],
        check=True,
    )

    if not is_downloaded(task):
        raise RuntimeError(
            f"Download finished but {target / 'motionplanning' / 'trajectory.h5'} "
            f"is missing. Check task ID."
        )
    return target


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--task", default="PickCube-v1")
    p.add_argument("--force", action="store_true",
                   help="Re-download even if already present")
    args = p.parse_args()
    out = run(task=args.task, force=args.force)
    print(f"\nDemos ready -> {out}")


if __name__ == "__main__":
    _cli()
