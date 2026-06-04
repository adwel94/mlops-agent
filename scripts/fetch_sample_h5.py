"""Fetch a ready-made sample trajectory HDF5 (official ManiSkill demo).

One of two ways to get an action trajectory into the project:
  - fetch_sample_h5 (here) — download an official demo from Hugging Face. Fast
    baseline / reference input. Only works for tasks ManiSkill ships demos for.
  - task_to_h5            — generate actions from scratch via motion planning.

Both land their output in the SAME place — `data/datasets/<task>/` inside the
project — so the consumer (`h5_add_images`) reads from one location regardless of
which producer made the file. ManiSkill's downloader writes to its own external
cache (~/.maniskill); this skill copies the result into the project so the
harness stays self-contained.

Output: data/datasets/<task>/trajectory.h5 (+ .json). The "trajectory" stem marks
it as a fetched demo (vs solve's "motionplanning"), recording the source.

Two interfaces:
  - Python:  from scripts.fetch_sample_h5 import run; run(task="PickCube-v1")
  - CLI:     python scripts/fetch_sample_h5.py --task PickCube-v1
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# ManiSkill's downloader writes here (external cache, not ours to control).
DEMOS_CACHE = Path.home() / ".maniskill" / "demos"
# Generated artifacts stay INSIDE the project so the harness is self-contained.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASETS_ROOT = PROJECT_ROOT / "data" / "datasets"


def _cache_h5(task: str) -> Path:
    return DEMOS_CACHE / task / "motionplanning" / "trajectory.h5"


def project_h5(task: str) -> Path:
    """Where the fetched demo lands inside the project."""
    return DATASETS_ROOT / task / "trajectory.h5"


def run(task: str = "PickCube-v1", force: bool = False) -> Path:
    """Download `task`'s official demo and copy it into data/datasets/<task>/.

    Returns the project-internal trajectory.h5 path (ready for h5_add_images).
    Idempotent: if the project copy already exists and not `force`, returns it.
    """
    dest = project_h5(task)
    if dest.exists() and not force:
        print(f"[fetch_sample_h5] {task}: already in project -> {dest}")
        return dest

    if not _cache_h5(task).exists() or force:
        print(f"[fetch_sample_h5] {task}: downloading via mani_skill.utils.download_demo ...")
        subprocess.run(
            [sys.executable, "-m", "mani_skill.utils.download_demo", task],
            check=True,
        )
    if not _cache_h5(task).exists():
        raise RuntimeError(
            f"Download finished but {_cache_h5(task)} is missing. Check task ID."
        )

    # Copy the demo (+ its JSON sidecar) into the project so all inputs to the
    # consumer pipeline live under data/ — no external dependency at replay time.
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_cache_h5(task), dest)
    src_json = _cache_h5(task).with_suffix(".json")
    if src_json.exists():
        shutil.copy2(src_json, dest.with_suffix(".json"))
    print(f"[fetch_sample_h5] {task}: copied into project -> {dest}")
    return dest


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--task", default="PickCube-v1")
    p.add_argument("--force", action="store_true",
                   help="Re-download / re-copy even if already present")
    args = p.parse_args()
    out = run(task=args.task, force=args.force)
    print(f"\nSample trajectory ready -> {out}")


if __name__ == "__main__":
    _cli()
