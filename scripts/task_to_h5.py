"""Generate an action trajectory from a task via ManiSkill motion planning (WSL).

`task_to_h5` is the producer that creates demos itself, as opposed to
`fetch_sample_h5` which downloads ready-made ones. Motion planning needs `mplib`,
which only ships Linux binaries, so the actual solving runs inside WSL; this
module is the Windows-side orchestrator that drives it and lands the output
inside the project's `data/` (self-contained).

Pipeline position:
    task_to_h5 (here) ->  trajectory (actions + env_states, NO images)
                      ->  h5_add_images (replay -> add RGB)  ->  dataset

Mechanism: invoke the WSL conda env's Python on a wrapper (reached over /mnt/c)
that runs the panda motion-planning solver headless on the software (llvmpipe)
Vulkan renderer. Built-in tasks use ManiSkill's run.py; this harness's custom
tasks use a seed-loop generator over scripts.custom_solutions. Output (.h5 +
.json) is written to the shared C: drive, then moved into data/datasets/<task>/.

Two interfaces:
  - Python:  from scripts.task_to_h5 import run; run(task="PickCube-v1", count=100)
  - CLI:     python scripts/task_to_h5.py --task PickCube-v1 --count 100
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# --- WSL environment constants (prerequisite, see README "WSL 환경 준비") --------
WSL_DISTRO = "Ubuntu-22.04"
WSL_PYTHON = "/root/miniconda3/envs/maniskill/bin/python"
# Force sapien onto the Mesa lavapipe software Vulkan ICD (WSL has no GPU Vulkan).
WSL_VK_ICD = "/usr/share/vulkan/icd.d/lvp_icd.x86_64.json"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASETS_ROOT = PROJECT_ROOT / "data" / "datasets"
WRAPPER = PROJECT_ROOT / "scripts" / "_wsl_solve_wrapper.py"
CUSTOM_WRAPPER = PROJECT_ROOT / "scripts" / "_wsl_solve_custom.py"

# Tasks ManiSkill ships a panda motion-planning solution for (run.py dispatch list).
BUILTIN_TASKS = [
    "PickCube-v1", "StackCube-v1", "PegInsertionSide-v1", "PlugCharger-v1",
    "PushCube-v1", "PullCube-v1", "PullCubeTool-v1", "LiftPegUpright-v1",
    "StackPyramid-v1", "PlaceSphere-v1", "DrawTriangle-v1", "DrawSVG-v1",
]
# This harness's custom envs with their own solution (scripts.custom_solutions).
CUSTOM_TASKS = [
    "ThreeColoredCubes-v1",
    "ColoredCubeInBowl-v1",
]
SUPPORTED_TASKS = BUILTIN_TASKS + CUSTOM_TASKS


def _win_to_wsl(p: Path) -> str:
    """C:\\Users\\x -> /mnt/c/Users/x"""
    p = p.resolve()
    drive = p.drive.rstrip(":").lower()        # 'C:' -> 'c'
    rest = p.as_posix()[len(p.drive):]          # '/Users/x'
    return f"/mnt/{drive}{rest}"


def run(
    task: str = "PickCube-v1",
    count: int = 100,
    traj_name: str = "motionplanning",
    obs_mode: str = "none",
    sim_backend: str = "cpu",
    only_success: bool = True,
    num_procs: int = 1,
    verbose: bool = False,
) -> Path:
    """Solve `task` `count` times via motion planning. Returns the produced .h5.

    The result is a raw trajectory (actions + env_states, obs_mode=none); feed it
    to `scripts.h5_add_images.run(task, traj_path=<this>)` to add RGB observations.
    """
    if task not in SUPPORTED_TASKS:
        raise ValueError(
            f"No motion-planning solution for '{task}'. "
            f"Supported: {', '.join(SUPPORTED_TASKS)}"
        )

    dest_dir = DATASETS_ROOT / task
    dest_dir.mkdir(parents=True, exist_ok=True)

    # both wrappers write to <record-dir>/<env-id>/motionplanning/<traj-name>.h5
    record_dir = DATASETS_ROOT
    produced = dest_dir / "motionplanning" / f"{traj_name}.h5"

    prefix = [f"export VK_ICD_FILENAMES={WSL_VK_ICD};", f'"{WSL_PYTHON}"']
    if task in CUSTOM_TASKS:
        # our own seed-loop generator over a custom solution
        inner = prefix + [
            f'"{_win_to_wsl(CUSTOM_WRAPPER)}"',
            "--task", task,
            "--count", str(count),
            "--obs-mode", obs_mode,
            "--sim-backend", sim_backend,
            "--record-dir", f'"{_win_to_wsl(record_dir)}"',
            "--traj-name", traj_name,
        ]
        if only_success:
            inner.append("--only-success")
    else:
        # ManiSkill's built-in run.py (panda solutions)
        inner = prefix + [
            f'"{_win_to_wsl(WRAPPER)}"',
            "-e", task,
            "-n", str(count),
            "-o", obs_mode,
            "-b", sim_backend,
            "--record-dir", f'"{_win_to_wsl(record_dir)}"',
            "--traj-name", traj_name,
            "--num-procs", str(num_procs),
        ]
        if only_success:
            inner.insert(-2, "--only-count-success")
    bash_cmd = " ".join(inner)

    if verbose:
        print(f"[task_to_h5] WSL command:\n  {bash_cmd}\n")

    proc = subprocess.run(
        ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", bash_cmd],
        # WSL emits UTF-8 (tqdm bars etc.); decoding as Windows' default cp949 would
        # mojibake/crash. errors='replace' keeps non-decodable bytes from raising.
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"[task_to_h5] WSL motion planning failed (exit {proc.returncode}).\n"
            f"--- stderr tail ---\n{proc.stderr[-2000:]}\n"
            f"Check that the WSL env is set up (see README 'WSL 환경 준비')."
        )

    # surface the solver's summary metrics (strip tqdm progress-bar glyphs that a
    # cp949 Windows console can't encode — keep only the ascii "key=val" tail)
    tail = [ln for ln in proc.stderr.splitlines() if "success_rate" in ln]
    if tail:
        last = tail[-1]
        metrics = last[last.find("success_rate"):].rstrip("] ")
        print("[task_to_h5] " + metrics.encode("ascii", "ignore").decode())

    if not produced.exists():
        raise RuntimeError(
            f"[task_to_h5] WSL run reported success but {produced} is missing.\n"
            f"--- stdout ---\n{proc.stdout[-1000:]}"
        )

    # flatten: data/datasets/<task>/motionplanning/<name>.h5 -> data/datasets/<task>/<name>.h5
    dest = dest_dir / f"{traj_name}.h5"
    for src_f, dst_f in [(produced, dest),
                         (produced.with_suffix(".json"), dest.with_suffix(".json"))]:
        if src_f.exists():
            if dst_f.exists():
                dst_f.unlink()
            shutil.move(str(src_f), str(dst_f))
    mp_dir = produced.parent
    if mp_dir.is_dir() and not any(mp_dir.iterdir()):
        mp_dir.rmdir()

    return dest


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--task", default="PickCube-v1")
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--traj-name", default="motionplanning")
    p.add_argument("--obs-mode", default="none")
    p.add_argument("--sim-backend", default="cpu")
    p.add_argument("--num-procs", type=int, default=1)
    p.add_argument("--all-attempts", action="store_true",
                   help="Keep failed attempts too (default: only successful)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    out = run(
        task=args.task,
        count=args.count,
        traj_name=args.traj_name,
        obs_mode=args.obs_mode,
        sim_backend=args.sim_backend,
        only_success=not args.all_attempts,
        num_procs=args.num_procs,
        verbose=args.verbose,
    )
    print(f"\nSolved trajectory -> {out}")


if __name__ == "__main__":
    _cli()
