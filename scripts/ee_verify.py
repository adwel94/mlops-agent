"""Verify 7d EE-delta actions reproduce task success via mplib IK (WSL).

Path-B EE pipeline, step (b). Converts a dataset's recorded joint trajectory to 7d
EE-delta (scripts.ee_convert) and replays it through per-step mplib IK in the sim,
checking that success still reproduces. mplib is Linux-only, so the executor runs
inside WSL (scripts/_wsl_ee_verify.py); this module is the Windows-side orchestrator
(mirrors scripts.task_to_h5's WSL-invocation pattern).

Input is the IMAGE dataset h5 (h5_add_images output) — it carries obs/extra/tcp_pose
which the conversion needs. Reports orig vs EE-execution success (reproduction rate).

  - Python:  from scripts.ee_verify import run; run("data/.../*.rgb.*.h5")
  - CLI:     python scripts/ee_verify.py --traj-path data/.../*.rgb.*.h5
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from scripts.task_to_h5 import WSL_DISTRO, WSL_PYTHON, WSL_VK_ICD, _win_to_wsl
except ImportError:  # run as a script: put project root on path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.task_to_h5 import WSL_DISTRO, WSL_PYTHON, WSL_VK_ICD, _win_to_wsl

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WSL_SCRIPT = PROJECT_ROOT / "scripts" / "_wsl_ee_verify.py"


def run(
    traj_path: str | Path,
    task: str | None = None,
    count: int = 10,
    seed: int = 0,
    sim_backend: str = "cpu",
    verbose: bool = False,
) -> dict:
    """Replay a random sample of `traj_path`'s episodes as EE-delta via mplib IK.

    This is a method gate: a random `count` episodes (reproducible via `seed`) confirm
    the EE+IK approach reproduces success for this task. `count=0` checks ALL episodes.
    `task` defaults to the sidecar's env_id.
    """
    traj_path = Path(traj_path)
    if not traj_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {traj_path}\n"
            f"Need an image dataset (h5_add_images output) with obs/extra/tcp_pose."
        )
    if task is None:
        meta = json.loads(traj_path.with_suffix(".json").read_text())
        task = meta["env_info"]["env_id"]

    inner = [
        f"export VK_ICD_FILENAMES={WSL_VK_ICD};", f'"{WSL_PYTHON}"',
        f'"{_win_to_wsl(WSL_SCRIPT)}"',
        "--task", task,
        "--traj-path", f'"{_win_to_wsl(traj_path)}"',
        "--count", str(count),
        "--seed", str(seed),
        "--sim-backend", sim_backend,
    ]
    bash_cmd = " ".join(inner)
    if verbose:
        print(f"[ee_verify] WSL command:\n  {bash_cmd}\n")

    proc = subprocess.run(
        ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", bash_cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(
            f"[ee_verify] WSL execution failed (exit {proc.returncode}).\n"
            f"--- stderr tail ---\n{proc.stderr[-2000:]}\n"
            f"Check the WSL env (see README 'WSL 환경 준비')."
        )

    m = re.search(r"DONE ee_verify (.+)", out)
    if not m:
        raise RuntimeError(
            f"[ee_verify] WSL run produced no result line.\n"
            f"--- output tail ---\n{out[-1500:]}"
        )
    line = m.group(1).strip()
    print("[ee_verify] " + line.encode("ascii", "ignore").decode())
    return dict(re.findall(r"(\w+)=(\S+)", line))


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--traj-path", required=True)
    p.add_argument("--task", default=None)
    p.add_argument("--count", type=int, default=10,
                   help="random sample size (method gate); 0 = all episodes")
    p.add_argument("--seed", type=int, default=0, help="reproducible random sample")
    p.add_argument("--sim-backend", default="cpu")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    run(args.traj_path, task=args.task, count=args.count, seed=args.seed,
        sim_backend=args.sim_backend, verbose=args.verbose)


if __name__ == "__main__":
    _cli()
