"""Re-execute one saved episode's actions in a live SAPIEN viewer.

Reads an episode's actions out of a trajectory HDF5, re-runs them in a cpu sim
seeded to that episode, and shows the result live in a desktop window. Use this
to watch what a recorded trajectory actually does. To just look at a task's scene
(no playback), use view_task.

Function mode SPAWNS the viewer as a background subprocess by default so a
notebook cell returns immediately. Pass ``blocking=True`` to run in-process and
block until the window closes.

Two interfaces:
  - Python:  from scripts.replay_h5 import run; run(traj_path=X, episode=0)
  - CLI:     python scripts/replay_h5.py --traj-path X --episode 0
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SHADER_DEFAULT = "default"


def _ensure_envs() -> None:
    """Register built-in + this project's custom environments.

    Works whether imported as a package module or run as a spawned subprocess
    script (sys.path[0] is then scripts/, so the project root is added to resolve
    scripts.custom_envs).
    """
    import importlib
    import os

    import mani_skill.envs  # noqa: F401  (registers built-in tasks)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    importlib.import_module("scripts.custom_envs")  # registers custom tasks


def _open(traj_path: Path, episode: int, shader: str) -> None:
    """Blocking in-process replay of one saved episode in the viewer."""
    import gymnasium as gym
    import h5py
    _ensure_envs()

    meta = json.loads(traj_path.with_suffix(".json").read_text())
    task = meta["env_info"]["env_id"]
    env_kwargs = meta["env_info"]["env_kwargs"]
    ctrl = env_kwargs.get("control_mode", "pd_joint_pos")
    if episode >= len(meta["episodes"]):
        raise IndexError(f"episode {episode} out of range ({len(meta['episodes'])} total)")
    ep_seed = meta["episodes"][episode]["episode_seed"]

    env = gym.make(
        task, num_envs=1, obs_mode="none", control_mode=ctrl,
        sim_backend="cpu", render_backend="cpu", render_mode="human",
        reward_mode="none", robot_uids="panda",
        enable_shadow=False,
        viewer_camera_configs=dict(shader_pack=shader),
    )
    env.reset(seed=ep_seed)

    with h5py.File(traj_path, "r") as f:
        traj_key = sorted(f.keys())[episode]
        actions = f[traj_key]["actions"][:]

    print(f"[replay_h5] replaying {traj_path.name} episode {episode} "
          f"({len(actions)} steps). Close the window to exit.", flush=True)
    viewer = env.unwrapped.render_human()
    try:
        for a in actions:
            if getattr(viewer, "closed", False):
                break
            env.step(a)
            env.unwrapped.render_human()
        while not getattr(viewer, "closed", False):  # hold final pose
            env.unwrapped.render_human()
    finally:
        env.close()


def _spawn(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *args])


def run(
    traj_path: str | Path,
    episode: int = 0,
    shader: str = SHADER_DEFAULT,
    blocking: bool = False,
) -> subprocess.Popen | None:
    """Live-replay one saved episode in the viewer. By default spawns a subprocess."""
    traj_path = Path(traj_path)
    if blocking:
        _open(traj_path, episode, shader)
        return None
    return _spawn(["--traj-path", str(traj_path),
                   "--episode", str(episode), "--shader", shader])


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--traj-path", required=True)
    p.add_argument("--episode", type=int, default=0)
    p.add_argument("--shader", default=SHADER_DEFAULT)
    args = p.parse_args()
    _open(Path(args.traj_path), args.episode, args.shader)


if __name__ == "__main__":
    _cli()
