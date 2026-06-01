"""Live SAPIEN viewer skill — open a desktop window for visual inspection.

Two modes (no teleoperation in this round; that needs pinocchio + IK):

  - browse(task)              Open viewer on a fresh task env. Robot does not
                              move; you orbit the camera with the mouse and
                              close the window when done.
  - replay(traj_path, episode) Re-execute one saved episode's actions in a
                              cpu sim and show it live in the viewer.

Both function-mode calls SPAWN the viewer as a background subprocess by
default so a notebook cell returns immediately. Pass ``blocking=True`` to
run in-process and block until the window closes.

CLI:
  python scripts/live.py browse --task PickCube-v1
  python scripts/live.py replay --traj-path X --episode 0
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SHADER_DEFAULT = "default"


def _open_browse(task: str, shader: str) -> None:
    """Blocking in-process implementation of browse. Used by CLI."""
    import gymnasium as gym
    import mani_skill.envs  # noqa: F401

    env = gym.make(
        task, num_envs=1, obs_mode="none", control_mode="pd_joint_pos",
        sim_backend="cpu", render_backend="cpu", render_mode="human",
        reward_mode="none", robot_uids="panda",
        enable_shadow=False,
        viewer_camera_configs=dict(shader_pack=shader),
    )
    env.reset(seed=0)
    print(f"[live] viewer open for {task}. Close the window to exit.", flush=True)
    try:
        viewer = env.unwrapped.render_human()
        while not getattr(viewer, "closed", False):
            env.unwrapped.render_human()
    finally:
        env.close()


def _open_replay(traj_path: Path, episode: int, shader: str) -> None:
    """Blocking in-process replay of one saved episode in the viewer."""
    import gymnasium as gym
    import mani_skill.envs  # noqa: F401
    import h5py

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

    print(f"[live] replaying {traj_path.name} episode {episode} "
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


def browse(
    task: str = "PickCube-v1",
    shader: str = SHADER_DEFAULT,
    blocking: bool = False,
) -> subprocess.Popen | None:
    """Open the viewer for ``task``. By default spawns a subprocess and returns it."""
    if blocking:
        _open_browse(task, shader)
        return None
    return _spawn(["browse", "--task", task, "--shader", shader])


def replay(
    traj_path: str | Path,
    episode: int = 0,
    shader: str = SHADER_DEFAULT,
    blocking: bool = False,
) -> subprocess.Popen | None:
    """Live-replay one saved episode in the viewer. By default spawns subprocess."""
    traj_path = Path(traj_path)
    if blocking:
        _open_replay(traj_path, episode, shader)
        return None
    return _spawn(["replay", "--traj-path", str(traj_path),
                   "--episode", str(episode), "--shader", shader])


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sp = p.add_subparsers(dest="mode", required=True)

    pb = sp.add_parser("browse", help="Open viewer on a task")
    pb.add_argument("--task", default="PickCube-v1")
    pb.add_argument("--shader", default=SHADER_DEFAULT)

    pr = sp.add_parser("replay", help="Live-replay one saved episode in viewer")
    pr.add_argument("--traj-path", required=True)
    pr.add_argument("--episode", type=int, default=0)
    pr.add_argument("--shader", default=SHADER_DEFAULT)

    args = p.parse_args()
    if args.mode == "browse":
        _open_browse(args.task, args.shader)
    else:
        _open_replay(Path(args.traj_path), args.episode, args.shader)


if __name__ == "__main__":
    _cli()
