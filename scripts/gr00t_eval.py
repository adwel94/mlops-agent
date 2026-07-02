"""Roll out a trained GR00T policy in sim and report task success rate.

Path-A deployment eval, step ④-eval. The GR00T policy (GPU) runs as a ZMQ server on
a remote box (RunPod); this orchestrator launches the rollout client
(scripts/_wsl_gr00t_eval.py — sim + IK, no torch), which connects to that server,
drives a closed-loop rollout, and reports success rate. On Windows the client runs
inside WSL (mplib IK + lavapipe Vulkan); on macOS/Linux it runs natively in the same
env (pinocchio IK — scripts.ik_exec picks the backend). Mirrors scripts.ee_verify's
invocation pattern.

Input is the SOURCE image dataset h5 (h5_add_images output) — not the lerobot dir —
because the rollout needs each episode's `episode_seed` (to reset the scene) and
`label_metadata` (to build the same instruction the model trained on). So the order is
h5_to_lerobot -> train (cloud) -> serve policy -> gr00t_eval against the source dataset.

Prereq (one-time, in the WSL maniskill env):  pip install pyzmq msgpack msgpack-numpy
Serve the policy on RunPod: cloud/serve/serve_policy.sh  (exposes tcp port).

  - Python:  from scripts.gr00t_eval import run; run("data/.../*.rgb.*.h5", server_host="...")
  - CLI:     python scripts/gr00t_eval.py --traj-path data/.../*.rgb.*.h5 --server-host <ip>
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# A2 라이브 스트리밍은 WSL child 의 출력(=tqdm 진행바의 부분블록 문자 ▏▏ 등)을 그대로
# Windows stdout 에 되쓴다. Windows 콘솔 기본 cp949 는 이 유니코드를 못 뱉어 UnicodeEncodeError
# 로 eval 전체가 죽는다 → utf-8 + errors=replace 로 재설정해 관측 코드가 실행을 깨지 않게 한다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from scripts.task_to_h5 import WSL_DISTRO, WSL_PYTHON, WSL_VK_ICD, _win_to_wsl
except ImportError:  # run as a script: put project root on path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.task_to_h5 import WSL_DISTRO, WSL_PYTHON, WSL_VK_ICD, _win_to_wsl

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WSL_SCRIPT = PROJECT_ROOT / "scripts" / "_wsl_gr00t_eval.py"


def run(
    traj_path: str | Path,
    server_host: str,
    server_port: int = 5555,
    task: str | None = None,
    count: int = 10,
    seed: int = 0,
    max_steps: int = 0,
    budget_factor: float = 3.0,
    action_steps: int = 16,
    instruction: str | None = None,
    sim_backend: str = "cpu",
    log_jsonl: str | Path | None = None,
    verbose: bool = False,
) -> dict:
    """Roll out the GR00T policy served at server_host:server_port over a sample of
    `traj_path`'s episodes, in sim via mplib IK, and report success rate.

    A random `count` episodes (reproducible via `seed`); `count=0` = all. `max_steps=0`
    uses each recorded episode's length * `budget_factor` (default 3x) as the step budget
    (the policy is slower per step than the planner, so 1x starves it); `max_steps>0` sets
    an absolute budget for all episodes. `instruction` is a template
    over the dataset's label_metadata keys (e.g. "pick up the {target_id} cube"); when
    omitted, the decoded label is used (must match what h5_to_lerobot trained on).
    `task` defaults to the sidecar's env_id.
    """
    traj_path = Path(traj_path)
    if not traj_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {traj_path}\n"
            f"Need the source image dataset (h5_add_images output) with obs/extra/tcp_pose, "
            f"episode_seed, and label_metadata — NOT the lerobot/ dir."
        )
    if task is None:
        meta = json.loads(traj_path.with_suffix(".json").read_text())
        task = meta["env_info"]["env_id"]

    # per-episode diagnostics default next to the dataset (any-pick / color / ik fails)
    if log_jsonl is None:
        log_jsonl = traj_path.parent / (traj_path.stem + ".eval_diag.jsonl")
    log_jsonl = Path(log_jsonl)

    if sys.platform == "win32":
        # Windows: 러너를 WSL 에서 (mplib + lavapipe Vulkan)
        inner = [
            f"export VK_ICD_FILENAMES={WSL_VK_ICD};", f'"{WSL_PYTHON}"',
            f'"{_win_to_wsl(WSL_SCRIPT)}"',
            "--task", task,
            "--traj-path", f'"{_win_to_wsl(traj_path)}"',
            "--server-host", server_host,
            "--server-port", str(server_port),
            "--count", str(count),
            "--seed", str(seed),
            "--max-steps", str(max_steps),
            "--budget-factor", str(budget_factor),
            "--action-steps", str(action_steps),
            "--sim-backend", sim_backend,
            "--log-jsonl", f'"{_win_to_wsl(log_jsonl)}"',
        ]
        if instruction:
            inner += ["--instruction", f'"{instruction}"']
        cmd = ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", " ".join(inner)]
    else:
        # macOS/Linux: 같은 env 의 파이썬으로 러너를 직접 실행 (WSL 계층 불필요;
        # IK 백엔드는 scripts.ik_exec 이 가용성으로 선택)
        cmd = [
            sys.executable, str(WSL_SCRIPT),
            "--task", task,
            "--traj-path", str(traj_path),
            "--server-host", server_host,
            "--server-port", str(server_port),
            "--count", str(count),
            "--seed", str(seed),
            "--max-steps", str(max_steps),
            "--budget-factor", str(budget_factor),
            "--action-steps", str(action_steps),
            "--sim-backend", sim_backend,
            "--log-jsonl", str(log_jsonl),
        ]
        if instruction:
            cmd += ["--instruction", instruction]
    if verbose:
        print(f"[gr00t_eval] command:\n  {cmd}\n")

    # A2: stream the runner output live (per-episode [ep] lines flush through) instead of
    # capturing silently — running-vs-stalled is visible in real time. stderr is merged
    # so the tqdm bar streams too. The full text is still accumulated to parse DONE.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    lines: list[str] = []
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        lines.append(line)
    proc.wait()
    out = "".join(lines)
    if proc.returncode != 0:
        raise RuntimeError(
            f"[gr00t_eval] runner execution failed (exit {proc.returncode}).\n"
            f"--- output tail ---\n{out[-2000:]}\n"
            f"Check: the env has pyzmq/msgpack/msgpack-numpy, and the policy server "
            f"is reachable at {server_host}:{server_port}."
        )

    m = re.search(r"DONE gr00t_eval (.+)", out)
    if not m:
        raise RuntimeError(
            f"[gr00t_eval] runner produced no result line.\n"
            f"--- output tail ---\n{out[-1500:]}"
        )
    line = m.group(1).strip()
    print("[gr00t_eval] " + line.encode("ascii", "ignore").decode())
    if log_jsonl.exists():
        print(f"[gr00t_eval] per-episode diagnostics: {log_jsonl}")
    return dict(re.findall(r"(\w+)=(\S+)", line))


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--traj-path", required=True)
    p.add_argument("--server-host", required=True,
                   help="host of the GR00T policy server (RunPod TCP proxy or tunnel)")
    p.add_argument("--server-port", type=int, default=5555)
    p.add_argument("--task", default=None)
    p.add_argument("--count", type=int, default=10,
                   help="random sample size; 0 = all episodes")
    p.add_argument("--seed", type=int, default=0, help="reproducible random sample")
    p.add_argument("--max-steps", type=int, default=0,
                   help="absolute per-episode step budget for all eps; 0 = factor-based (see --budget-factor)")
    p.add_argument("--budget-factor", type=float, default=3.0,
                   help="when --max-steps=0, budget = recorded episode length * this (default 3x)")
    p.add_argument("--action-steps", type=int, default=16,
                   help="actions executed per replan (<= GR00T action horizon)")
    p.add_argument("--instruction", default=None,
                   help="template over label_metadata keys, e.g. \"pick up the {target_id} cube\"")
    p.add_argument("--sim-backend", default="cpu")
    p.add_argument("--log-jsonl", default=None,
                   help="per-episode diagnostics output (default: <dataset>.eval_diag.jsonl)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    run(args.traj_path, server_host=args.server_host, server_port=args.server_port,
        task=args.task, count=args.count, seed=args.seed, max_steps=args.max_steps,
        budget_factor=args.budget_factor, action_steps=args.action_steps,
        instruction=args.instruction,
        sim_backend=args.sim_backend, log_jsonl=args.log_jsonl, verbose=args.verbose)


if __name__ == "__main__":
    _cli()
