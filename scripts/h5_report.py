"""Generate a Markdown data-quality report for a dataset HDF5.

Picks N random episodes from an image-bearing dataset (h5_add_images output) and,
for each, writes: a metadata table, an INLINE filmstrip PNG (sample card), and a
link to an MP4. The report lets a human eyeball (image + instruction + action)
alignment that raw numbers can't reveal — the recommended pre-training guardrail.

Task-agnostic: the instruction/labels are decoded from the dataset's env-declared
`label_metadata` (no task name is referenced). Builds on scripts.h5_to_media's
reusable renderers (card/video).

Function:  run(traj_path, n=3, seed=None, fps=15, out=None) -> Path
CLI:       python scripts/h5_report.py --traj-path X --n 3
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

import numpy as np

try:
    from scripts.h5_to_media import card, video
except ImportError:  # run as a script: put project root on path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.h5_to_media import card, video


def _episode_indices(trajs: list[str]) -> list[int]:
    """traj_<i> keys -> sorted integer indices (robust to dict ordering)."""
    return sorted(int(k.split("_")[1]) for k in trajs)


def run(
    traj_path: str | Path,
    n: int = 3,
    seed: int | None = None,
    fps: int = 15,
    out: str | Path | None = None,
) -> Path:
    """Write a Markdown report sampling `n` random episodes. Returns the .md path."""
    import h5py

    traj_path = Path(traj_path)
    sidecar = json.loads(traj_path.with_suffix(".json").read_text())
    env_info = sidecar.get("env_info", {})
    env_id = env_info.get("env_id", "?")
    ctrl = env_info.get("env_kwargs", {}).get("control_mode", "?")
    label_md = sidecar.get("label_metadata") or {}
    eps_meta = sidecar.get("episodes", [])

    # gather metadata for chosen episodes in a single pass (card/video reopen later)
    with h5py.File(traj_path, "r") as f:
        all_idx = _episode_indices(list(f.keys()))
        n = min(n, len(all_idx))
        chosen = sorted(random.Random(seed).sample(all_idx, n))
        total = len(all_idx)
        n_success_total = 0
        for i in all_idx:
            ep = f[f"traj_{i}"]
            if "success" in ep and bool(np.asarray(ep["success"])[-1]):
                n_success_total += 1

        meta_rows = []
        for i in chosen:
            ep = f[f"traj_{i}"]
            steps, adim = ep["actions"].shape
            try:
                sdim = ep["obs"]["agent"]["qpos"].shape[1]
            except Exception:
                sdim = None
            success = bool(np.asarray(ep["success"])[-1]) if "success" in ep else None
            decoded = {}
            extra = ep["obs"].get("extra", {})
            for key, names in label_md.items():
                try:
                    decoded[key] = names[int(np.asarray(extra[key])[0])]
                except Exception:
                    pass
            seed_i = None
            if i < len(eps_meta):
                seed_i = eps_meta[i].get("episode_seed")
            meta_rows.append(dict(idx=i, steps=int(steps), adim=int(adim), sdim=sdim,
                                  success=success, decoded=decoded, seed=seed_i))

    reports_dir = traj_path.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = traj_path.stem

    lines = [
        f"# Data-quality report — {env_id}",
        "",
        f"- dataset: `{traj_path.name}`",
        f"- control_mode: `{ctrl}`",
        f"- episodes: **{total}** total, success **{n_success_total}/{total}** "
        f"({n_success_total / total:.0%})" if total else "- episodes: 0",
        f"- sampled: **{n}** random episode(s)"
        + (f" (seed={seed})" if seed is not None else ""),
        f"- label_metadata: `{label_md or 'none'}`",
        "",
        "---",
        "",
    ]

    for m in meta_rows:
        i = m["idx"]
        card_png = card(traj_path, episode=i,
                        out=reports_dir / f"{stem}.ep{i:04d}.card.png")
        mp4 = video(traj_path, episode=i, fps=fps,
                    out=reports_dir / f"{stem}.ep{i:04d}.mp4")

        instr = ", ".join(f"{k}={v}" for k, v in m["decoded"].items()) or "(none)"
        lines += [
            f"## episode traj_{i}",
            "",
            "| field | value |",
            "|---|---|",
            f"| instruction (decoded) | {instr} |",
            f"| success | {m['success']} |",
            f"| steps | {m['steps']} |",
            f"| seed | {m['seed']} |",
            f"| action dim | {m['adim']} |",
            f"| state dim | {m['sdim']} |",
            "",
            f"![filmstrip]({card_png.name})",
            "",
            f"[▶ video: {mp4.name}]({mp4.name})",
            "",
            "---",
            "",
        ]

    out_path = Path(out) if out else reports_dir / f"{stem}.report.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--traj-path", required=True)
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--out", default=None)
    args = p.parse_args()
    out = run(args.traj_path, n=args.n, seed=args.seed, fps=args.fps, out=args.out)
    print(f"\nh5_report -> {out}")


if __name__ == "__main__":
    _cli()
