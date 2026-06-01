"""Render media (MP4 video / PNG grid) from a saved trajectory HDF5.

No simulator runs here — reads pre-recorded RGB frames out of the HDF5 and
assembles them into a media file. Designed for inline notebook display.

Two functions:
  - video(traj_path, episode=0, out=None, fps=30) -> Path
  - preview(traj_path, n=9, out=None, frame='mid') -> Path

CLI:
  python scripts/render.py video --traj-path X --episode 0
  python scripts/render.py preview --traj-path X --n 9
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal


def _open_traj_and_camera(traj_path: Path):
    import h5py
    f = h5py.File(traj_path, "r")
    trajs = sorted(f.keys())
    if not trajs:
        f.close()
        raise ValueError(f"No episodes in {traj_path}")
    sd = f[trajs[0]].get("obs", {}).get("sensor_data")
    if sd is None or len(sd.keys()) == 0:
        f.close()
        raise ValueError(f"No sensor_data/camera in {traj_path} (was obs_mode=rgb used?)")
    return f, trajs, list(sd.keys())[0]


def video(
    traj_path: str | Path,
    episode: int = 0,
    out: str | Path | None = None,
    fps: int = 30,
    camera: str | None = None,
) -> Path:
    """Encode one episode's RGB frames to an MP4. Returns the output Path."""
    import imageio.v2 as imageio

    traj_path = Path(traj_path)
    f, trajs, default_cam = _open_traj_and_camera(traj_path)
    cam = camera or default_cam

    with f:
        if episode >= len(trajs):
            raise IndexError(f"episode {episode} out of range (have {len(trajs)})")
        rgb = f[trajs[episode]]["obs"]["sensor_data"][cam]["rgb"][:]

    out_path = Path(out) if out else traj_path.with_suffix("").with_name(
        f"{traj_path.stem}.ep{episode:04d}.mp4")

    with imageio.get_writer(out_path, fps=fps, codec="libx264", quality=8) as w:
        for frame in rgb:
            w.append_data(frame)
    return out_path


def preview(
    traj_path: str | Path,
    n: int = 9,
    out: str | Path | None = None,
    frame: Literal["first", "mid", "last"] = "mid",
    camera: str | None = None,
) -> Path:
    """Save a square-ish PNG grid of one frame per episode (n episodes)."""
    import numpy as np
    from PIL import Image

    traj_path = Path(traj_path)
    f, trajs, default_cam = _open_traj_and_camera(traj_path)
    cam = camera or default_cam

    take = trajs[:n]
    frames = []
    with f:
        for k in take:
            rgb_ds = f[k]["obs"]["sensor_data"][cam]["rgb"]
            T = rgb_ds.shape[0]
            idx = {"first": 0, "mid": T // 2, "last": T - 1}[frame]
            frames.append(rgb_ds[idx][:])

    H, W, _ = frames[0].shape
    cols = int(np.ceil(np.sqrt(len(frames))))
    rows = int(np.ceil(len(frames) / cols))
    grid = np.zeros((rows * H, cols * W, 3), dtype=np.uint8)
    for i, fr in enumerate(frames):
        r, c = divmod(i, cols)
        grid[r * H:(r + 1) * H, c * W:(c + 1) * W] = fr

    out_path = Path(out) if out else traj_path.with_suffix("").with_name(
        f"{traj_path.stem}.preview_{frame}_{len(frames)}.png")
    Image.fromarray(grid).save(out_path)
    return out_path


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sp = p.add_subparsers(dest="mode", required=True)

    pv = sp.add_parser("video", help="Encode one episode to MP4")
    pv.add_argument("--traj-path", required=True)
    pv.add_argument("--episode", type=int, default=0)
    pv.add_argument("--out", default=None)
    pv.add_argument("--fps", type=int, default=30)
    pv.add_argument("--camera", default=None)

    pp = sp.add_parser("preview", help="Save a PNG grid of N episodes")
    pp.add_argument("--traj-path", required=True)
    pp.add_argument("--n", type=int, default=9)
    pp.add_argument("--out", default=None)
    pp.add_argument("--frame", choices=["first", "mid", "last"], default="mid")
    pp.add_argument("--camera", default=None)

    args = p.parse_args()
    if args.mode == "video":
        out = video(args.traj_path, args.episode, args.out, args.fps, args.camera)
    else:
        out = preview(args.traj_path, args.n, args.out, args.frame, args.camera)
    print(f"\nrender -> {out}")


if __name__ == "__main__":
    _cli()
