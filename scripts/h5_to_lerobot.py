"""Convert an image dataset HDF5 into a GR00T-flavored LeRobot v2.1 dataset (Path A).

Reads an h5_add_images output (rgb + obs/extra/tcp_pose + joint actions + per-episode
success/seed) and packages it into the LeRobot v2.1 layout (+ GR00T's meta/modality.json):

    <out>/
      meta/{info.json, episodes.jsonl, tasks.jsonl, modality.json, stats.json}
      data/chunk-000/episode_{i:06d}.parquet      # state, action, indices per step
      videos/chunk-000/observation.images.<cam>/episode_{i:06d}.mp4

ACTION (10d, ABSOLUTE end-effector): [xyz(3), rot6d(6), gripper(1)] — GR00T's XYZ_ROT6D
EEF format (scripts.ee_convert.episode_to_abs_eef). We store the ABSOLUTE next-step pose;
GR00T's rep=RELATIVE + state_key relativizes it internally (we do NOT pre-delta).
STATE (qpos + abs EEF): [qpos(Q), eef_abs(9)] — the eef block is the relativization
reference (state_key="eef"). action[t]=pose[t+1], state[t]=pose[t]; N=T-1.

Pure offline (no sim, no WSL); uses pyarrow + imageio (already installed) — no lerobot
dependency, so the working conda env stays untouched. Targets codebase_version v2.1
(meta schema matched to Isaac-GR00T's demo_data/cube_to_bowl_5). Final load-compatibility
is validated when GR00T ingests it (training box); regenerate stats/relative_stats with
scripts/repair_lerobot_metadata.py there.

Task-agnostic: the language instruction is built from the dataset's env-declared
`label_metadata` via an `instruction` template (default emits the decoded label).

  - Python:  from scripts.h5_to_lerobot import run; run("data/.../*.rgb.*.h5")
  - CLI:     python scripts/h5_to_lerobot.py --traj-path data/.../*.rgb.*.h5
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

try:
    from scripts.ee_convert import episode_to_abs_eef
except ImportError:  # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.ee_convert import episode_to_abs_eef

CODEBASE_VERSION = "v2.1"
CHUNK_SIZE = 1000
# 임베디먼트의 정규 카메라 이름 — new_embodiment_config.py 의 video modality_key 와 일치해야 함.
# 카메라는 **이름으로** 고른다(위치 X): base_camera 가 몇 번째에 있든 상관없고, 없으면 에러.
# (validate_custom_task.py 가 이 상수를 import 해 "존재" 검사에 쓴다 — 단일 출처.)
BASE_CAMERA = "base_camera"


def _instruction(decoded: dict, template: str | None, fallback: str) -> str:
    """Language string for one episode, from decoded label_metadata."""
    if template:
        try:
            return template.format(**decoded)
        except Exception:
            pass
    if decoded:
        return ", ".join(str(v) for v in decoded.values())
    return fallback


def _stats_block(arr: np.ndarray) -> dict:
    """min/max/mean/std/q01/q99 for a (N, D) float feature (GR00T/LeRobot stats format).

    Matches the official example's per-feature keys. GR00T's loader requires stats.json
    to exist; for the canonical normalization (incl. relative_stats.json for our delta
    actions) regenerate with scripts/repair_lerobot_metadata.py in the gr00t env.
    """
    a = np.asarray(arr, dtype=np.float64)
    return {
        "min": a.min(0).tolist(), "max": a.max(0).tolist(),
        "mean": a.mean(0).tolist(), "std": a.std(0).tolist(),
        "q01": np.quantile(a, 0.01, axis=0).tolist(),
        "q99": np.quantile(a, 0.99, axis=0).tolist(),
    }


def run(
    traj_path: str | Path,
    out: str | Path | None = None,
    fps: int = 20,
    instruction: str | None = None,
    camera: str | None = None,
) -> Path:
    """Build a GR00T LeRobot v2.1 dataset (absolute EEF actions) from a dataset h5. Returns out dir."""
    import h5py
    import imageio.v2 as imageio
    import pyarrow as pa
    import pyarrow.parquet as pq

    traj_path = Path(traj_path)
    sidecar = json.loads(traj_path.with_suffix(".json").read_text())
    env_info = sidecar.get("env_info", {})
    env_id = env_info.get("env_id", "unknown")
    label_md = sidecar.get("label_metadata") or {}

    out = Path(out) if out else traj_path.parent / "lerobot"
    data_dir = out / "data" / "chunk-000"
    meta_dir = out / "meta"
    data_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    f = h5py.File(traj_path, "r")
    keys = sorted(f.keys(), key=lambda k: int(k.split("_")[1]))
    # 카메라는 위치(keys[0])가 아니라 **이름**으로 고른다 — base_camera 가 몇 번째든 OK.
    # 데이터셋에 그 이름이 없으면 조용히 엉뚱한 카메라를 쓰지 말고 즉시 에러(또는 camera= 명시).
    available = list(f[keys[0]]["obs"]["sensor_data"].keys())
    cam = camera or BASE_CAMERA
    if cam not in available:
        f.close()
        raise ValueError(
            f"카메라 {cam!r} 가 데이터셋에 없습니다. 사용 가능: {available}. "
            f"정규 카메라명은 {BASE_CAMERA!r}(new_embodiment_config 와 일치). "
            f"환경의 주 카메라를 {BASE_CAMERA!r} 로 두거나, 다른 카메라를 쓰려면 camera=/--camera 로 명시하세요."
        )
    video_key = f"observation.images.{cam}"
    vid_dir = out / "videos" / "chunk-000" / video_key
    vid_dir.mkdir(parents=True, exist_ok=True)

    tasks: dict[str, int] = {}          # instruction -> task_index (first-seen order)
    episodes_meta = []                  # for episodes.jsonl
    state_all, action_all, ts_all = [], [], []   # for stats
    H = W = 0
    global_idx = 0
    qpos_dim = state_dim = action_dim = 0

    for i_key in keys:
        i = int(i_key.split("_")[1])
        ep = f[i_key]
        rgb = ep["obs"]["sensor_data"][cam]["rgb"][:]          # (T,H,W,3) uint8
        qpos = ep["obs"]["agent"]["qpos"][:]                   # (T,Q)
        tcp = ep["obs"]["extra"]["tcp_pose"][:]                # (T,7)
        act = ep["actions"][:]                                 # (T-1,A) joint
        abs_eef = episode_to_abs_eef(tcp).astype(np.float32)   # (T,9) absolute xyz+rot6d
        n = act.shape[0]                                       # = T-1
        gripper = act[:, -1:].astype(np.float32)               # (N,1) gripper command
        action = np.concatenate([abs_eef[1:1 + n], gripper], axis=1)              # (N,10): pose[t+1]+gripper
        state = np.concatenate([qpos[:n].astype(np.float32), abs_eef[:n]], axis=1)  # (N,Q+9): pose[t]+qpos
        frames = rgb[:n]                                       # (N,H,W,3)
        H, W = frames.shape[1], frames.shape[2]
        qpos_dim = qpos.shape[1]
        state_dim = state.shape[1]
        action_dim = action.shape[1]

        # instruction from declared labels -> task_index
        decoded = {}
        extra = ep["obs"].get("extra", {})
        for k_lab, names in label_md.items():
            try:
                decoded[k_lab] = names[int(np.asarray(extra[k_lab])[0])]
            except Exception:
                pass
        instr = _instruction(decoded, instruction, env_id)
        tidx = tasks.setdefault(instr, len(tasks))

        # video: N frames -> mp4
        mp4 = vid_dir / f"episode_{i:06d}.mp4"
        with imageio.get_writer(mp4, fps=fps, codec="libx264",
                                macro_block_size=1, ffmpeg_log_level="error") as w:
            for fr in frames:
                w.append_data(fr)

        # parquet: one row per step
        table = pa.table({
            "observation.state": pa.array([r.tolist() for r in state], type=pa.list_(pa.float32())),
            "action": pa.array([r.tolist() for r in action], type=pa.list_(pa.float32())),
            "timestamp": pa.array((np.arange(n) / fps).astype(np.float32)),
            "frame_index": pa.array(np.arange(n, dtype=np.int64)),
            "episode_index": pa.array(np.full(n, i, np.int64)),
            "index": pa.array(np.arange(global_idx, global_idx + n, dtype=np.int64)),
            "task_index": pa.array(np.full(n, tidx, np.int64)),
        })
        pq.write_table(table, data_dir / f"episode_{i:06d}.parquet")

        # accumulate stats
        state_all.append(state)
        action_all.append(action)
        ts_all.append((np.arange(n) / fps).astype(np.float64))
        episodes_meta.append({"episode_index": i, "tasks": [instr], "length": n})
        global_idx += n

    f.close()
    total_frames = global_idx
    total_episodes = len(keys)

    # ---- meta files ----
    (meta_dir / "tasks.jsonl").write_text(
        "\n".join(json.dumps({"task_index": idx, "task": t}) for t, idx in tasks.items()),
        encoding="utf-8")
    (meta_dir / "episodes.jsonl").write_text(
        "\n".join(json.dumps(e) for e in episodes_meta), encoding="utf-8")

    info = {
        "codebase_version": CODEBASE_VERSION,
        "robot_type": "panda",
        "total_episodes": total_episodes,
        "total_frames": total_frames,
        "total_tasks": len(tasks),
        "total_videos": total_episodes,
        "total_chunks": 1,
        "chunks_size": CHUNK_SIZE,
        "fps": fps,
        "splits": {"train": f"0:{total_episodes}"},
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
        "features": {
            video_key: {
                "dtype": "video", "shape": [H, W, 3],
                "names": ["height", "width", "channels"],
                "info": {"video.height": H, "video.width": W, "video.channels": 3,
                         "video.codec": "h264", "video.pix_fmt": "yuv420p",
                         "video.is_depth_map": False, "video.fps": float(fps),
                         "has_audio": False},
            },
            "observation.state": {"dtype": "float32", "shape": [state_dim],
                                  "names": ([f"qpos_{k}" for k in range(qpos_dim)]
                                            + ["eef_x", "eef_y", "eef_z"]
                                            + [f"eef_rot6d_{k}" for k in range(6)])},
            "action": {"dtype": "float32", "shape": [action_dim],
                       "names": ["eef_x", "eef_y", "eef_z"]
                                + [f"eef_rot6d_{k}" for k in range(6)] + ["gripper"]},
            "timestamp": {"dtype": "float32", "shape": [1], "names": None},
            "frame_index": {"dtype": "int64", "shape": [1], "names": None},
            "episode_index": {"dtype": "int64", "shape": [1], "names": None},
            "index": {"dtype": "int64", "shape": [1], "names": None},
            "task_index": {"dtype": "int64", "shape": [1], "names": None},
        },
    }
    (meta_dir / "info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")

    # GR00T modality.json. action eef is ABSOLUTE xyz+rot6d (9d); the state "eef" block
    # (same 9d format) is the relativization reference (config: state_key="eef").
    modality = {
        "state": {"qpos": {"start": 0, "end": qpos_dim},
                  "eef": {"start": qpos_dim, "end": qpos_dim + 9}},
        "action": {"eef": {"start": 0, "end": 9},
                   "gripper": {"start": 9, "end": 10}},
        "video": {cam: {"original_key": video_key}},
        "annotation": {"human.task_description": {"original_key": "task_index"}},
    }
    (meta_dir / "modality.json").write_text(json.dumps(modality, indent=2), encoding="utf-8")

    # stats.json (normalization). Matches the official example's keys: numeric features
    # only (action, observation.state, timestamp); images are normalized by GR00T's vision
    # encoder, not via stats. The loader requires this file to exist — for canonical stats
    # + relative_stats.json (EEF relative actions), regenerate with repair_lerobot_metadata.py.
    stats = {
        "observation.state": _stats_block(np.concatenate(state_all)),
        "action": _stats_block(np.concatenate(action_all)),
        "timestamp": _stats_block(np.concatenate(ts_all).reshape(-1, 1)),
    }
    (meta_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    print(f"[h5_to_lerobot] {env_id}: {total_episodes} episodes, {total_frames} frames "
          f"-> {out}")
    print(f"[h5_to_lerobot] tasks ({len(tasks)}): "
          + "; ".join(f"{idx}:{t}" for t, idx in tasks.items()))
    print(f"[h5_to_lerobot] action={action_dim}d abs-EEF (xyz+rot6d+gripper), "
          f"state={state_dim}d (qpos{qpos_dim}+eef9), video={video_key} {H}x{W}")
    return out


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--traj-path", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--fps", type=int, default=20)
    p.add_argument("--instruction", default=None,
                   help="template using label_metadata keys, e.g. \"pick up the {target_id} cube\"")
    p.add_argument("--camera", default=None)
    args = p.parse_args()
    out = run(args.traj_path, out=args.out, fps=args.fps,
              instruction=args.instruction, camera=args.camera)
    print(f"\nLeRobot dataset -> {out}")


if __name__ == "__main__":
    _cli()
