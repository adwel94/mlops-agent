"""Open a live SAPIEN viewer on a fresh task environment (visual inspection).

No teleoperation (that needs pinocchio + IK): the robot does not move; you orbit
the camera with the mouse and close the window when done. Use this to eyeball a
task's scene / cube layout before generating data. To watch a recorded episode
play back instead, use replay_h5.

Function mode SPAWNS the viewer as a background subprocess by default so a
notebook cell returns immediately. Pass ``blocking=True`` to run in-process and
block until the window closes.

Two interfaces:
  - Python:  from scripts.view_task import run; run(task="ThreeColoredCubes-v1")
  - CLI:     python scripts/view_task.py --task ThreeColoredCubes-v1
"""
from __future__ import annotations

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


def _open(task: str, shader: str) -> None:
    """Blocking in-process viewer on a task env. Used by CLI / blocking mode."""
    import gymnasium as gym
    _ensure_envs()

    env = gym.make(
        task, num_envs=1, obs_mode="none", control_mode="pd_joint_pos",
        sim_backend="cpu", render_backend="cpu", render_mode="human",
        reward_mode="none", robot_uids="panda",
        enable_shadow=False,
        viewer_camera_configs=dict(shader_pack=shader),
    )
    env.reset(seed=0)
    print(f"[view_task] viewer open for {task}. Close the window to exit.", flush=True)
    try:
        viewer = env.unwrapped.render_human()
        while not getattr(viewer, "closed", False):
            env.unwrapped.render_human()
    finally:
        env.close()


def _spawn(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *args])


def run(
    task: str = "PickCube-v1",
    shader: str = SHADER_DEFAULT,
    blocking: bool = False,
) -> subprocess.Popen | None:
    """Open the viewer for ``task``. By default spawns a subprocess and returns it."""
    if blocking:
        _open(task, shader)
        return None
    return _spawn(["--task", task, "--shader", shader])


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--task", default="PickCube-v1")
    p.add_argument("--shader", default=SHADER_DEFAULT)
    args = p.parse_args()
    _open(args.task, args.shader)


if __name__ == "__main__":
    _cli()
