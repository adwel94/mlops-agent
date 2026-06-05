"""Render media (MP4 video / PNG grid) from a saved dataset HDF5.

No simulator runs here — reads pre-recorded RGB frames out of the HDF5 and
assembles them into a media file. Designed for inline notebook display.

Reusable rendering library (the h5_report skill builds on these):
  - video(traj_path, episode=0, out=None, fps=30) -> Path
  - preview(traj_path, n=9, out=None, frame='mid') -> Path
  - card(traj_path, episode=0, n=12, out=None) -> Path   # labeled filmstrip

CLI:
  python scripts/h5_to_media.py video --traj-path X --episode 0
  python scripts/h5_to_media.py preview --traj-path X --n 9
  python scripts/h5_to_media.py card --traj-path X --episode 0
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal


def _open_traj_and_camera(traj_path: Path):
    import h5py
    f = h5py.File(traj_path, "r")
    # numeric sort: keys are traj_<i>; plain sorted() is lexicographic and would put
    # traj_10 before traj_2, breaking episode-index addressing for >=10 episodes.
    trajs = sorted(f.keys(), key=lambda k: int(k.split("_")[1]))
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


def card(
    traj_path: str | Path,
    episode: int = 0,
    n: int = 12,
    out: str | Path | None = None,
    camera: str | None = None,
) -> Path:
    """Save a labeled filmstrip PNG for one episode (data-quality 'sample card').

    N frames sampled across the episode in a grid; the title is built from the
    dataset's env-declared `label_metadata` decoded against obs/extra (e.g.
    target_id=red), and each frame's border is a best-effort gripper proxy from the
    last qpos dim, normalized within the episode. Fully task-agnostic: no task name
    is referenced; envs without label_metadata/qpos just get a plainer card.
    """
    import json
    import numpy as np
    from PIL import Image, ImageDraw

    traj_path = Path(traj_path)
    f, trajs, default_cam = _open_traj_and_camera(traj_path)
    cam = camera or default_cam

    label_md = {}
    sidecar = traj_path.with_suffix(".json")
    if sidecar.exists():
        label_md = json.loads(sidecar.read_text()).get("label_metadata") or {}

    with f:
        if episode >= len(trajs):
            raise IndexError(f"episode {episode} out of range (have {len(trajs)})")
        ep = f[trajs[episode]]
        rgb = ep["obs"]["sensor_data"][cam]["rgb"][:]
        try:
            grip = ep["obs"]["agent"]["qpos"][:, -1]   # generic gripper proxy
        except Exception:
            grip = None
        labels_txt = []
        extra = ep["obs"].get("extra", {})
        for key, names in label_md.items():
            try:
                v = int(np.asarray(extra[key])[0])
                labels_txt.append(f"{key}={names[v]}")
            except Exception:
                pass

    T = rgb.shape[0]
    n = min(n, T)
    idxs = np.linspace(0, T - 1, n).astype(int)
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    cell, bar, pad, title_h = 160, 22, 6, 30

    W = cols * (cell + pad) + pad
    H = title_h + rows * (cell + bar + pad) + pad
    canvas = Image.new("RGB", (W, H), (24, 24, 28))
    draw = ImageDraw.Draw(canvas)
    title = "  |  ".join(labels_txt) if labels_txt else trajs[episode]
    draw.text((pad + 2, 8), f"{title}    ({trajs[episode]}, {T} frames)", fill=(255, 255, 255))

    gmin = float(grip.min()) if grip is not None else 0.0
    grng = (float(grip.max()) - gmin) if grip is not None else 0.0

    for i, t in enumerate(idxs):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = title_h + r * (cell + bar + pad)
        if grip is not None and grng > 1e-6:
            openness = (float(grip[t]) - gmin) / grng
            border = (60, 200, 90) if openness > 0.5 else (220, 70, 70)
            cap = f"t={t}  grip:{float(grip[t]):.3f}"
        else:
            border = (120, 120, 130)
            cap = f"t={t}"
        img = Image.fromarray(rgb[t]).resize((cell, cell), Image.NEAREST)
        canvas.paste(img, (x, y))
        draw.rectangle([x, y, x + cell - 1, y + cell - 1], outline=border, width=3)
        draw.rectangle([x, y + cell, x + cell, y + cell + bar], fill=(40, 40, 46))
        draw.text((x + 4, y + cell + 5), cap, fill=border)

    out_path = Path(out) if out else traj_path.with_suffix("").with_name(
        f"{traj_path.stem}.card_ep{episode:04d}.png")
    canvas.save(out_path)
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

    pc = sp.add_parser("card", help="Save a labeled filmstrip PNG for one episode")
    pc.add_argument("--traj-path", required=True)
    pc.add_argument("--episode", type=int, default=0)
    pc.add_argument("--n", type=int, default=12)
    pc.add_argument("--out", default=None)
    pc.add_argument("--camera", default=None)

    args = p.parse_args()
    if args.mode == "video":
        out = video(args.traj_path, args.episode, args.out, args.fps, args.camera)
    elif args.mode == "card":
        out = card(args.traj_path, args.episode, args.n, args.out, args.camera)
    else:
        out = preview(args.traj_path, args.n, args.out, args.frame, args.camera)
    print(f"\nh5_to_media -> {out}")


if __name__ == "__main__":
    _cli()
