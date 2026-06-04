"""WSL grasp test: can the arm actually pick a chosen colored cube?

Runs the PickCube-style motion-planning recipe (reach -> grasp -> close -> lift)
but targeting one specific cube in ThreeColoredCubes-v1, captures a frame at each
phase, and reports whether the grasp held. mplib + software (llvmpipe) Vulkan, so
this runs inside WSL.

The target cube is chosen by the ENV from the seed (env.target_id), so the same
seed always grasps the same cube — exactly what flows through to the dataset.

Usage (inside WSL):
  python _wsl_grasp_test.py <seed>      e.g.  python _wsl_grasp_test.py 0
"""
import sys

# --- project root so scripts.custom_envs is importable over /mnt/c ----------
PROJECT_ROOT = "/mnt/c/Users/hun41/PycharmProjects/maniskill"
sys.path.insert(0, PROJECT_ROOT)

# --- RenderSystem fallback: WSL only has llvmpipe; let sapien auto-select it -
import sapien.render as _R
_orig_rs = _R.RenderSystem
def _safe_rs(*a, **k):
    try:
        return _orig_rs(*a, **k)
    except RuntimeError:
        return _orig_rs()
_R.RenderSystem = _safe_rs

import numpy as np
import imageio.v2 as imageio
import sapien
import gymnasium as gym

import mani_skill.envs  # noqa: F401
import scripts.custom_envs  # noqa: F401  (registers ThreeColoredCubes-v1)
from scripts.custom_envs import CUBE_COLORS
from mani_skill.examples.motionplanning.panda.motionplanner import (
    PandaArmMotionPlanningSolver,
)
from mani_skill.examples.motionplanning.base_motionplanner.utils import (
    compute_grasp_info_by_obb, get_actor_obb,
)

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 0
FINGER_LENGTH = 0.025

env = gym.make(
    "ThreeColoredCubes-v1", obs_mode="none", control_mode="pd_joint_pos",
    sim_backend="cpu", render_backend="cpu", render_mode="rgb_array",
    reward_mode="none",
)
env.reset(seed=SEED)
base = env.unwrapped

# target is decided by the env from the seed (not passed in)
TARGET = base.target_color()
target = base.cubes[int(base.target_id[0])]
init_cube_z = float(target.pose.p[0, 2])

planner = PandaArmMotionPlanningSolver(
    env, debug=False, vis=False,
    base_pose=base.agent.robot.pose,
    visualize_target_grasp_pose=False, print_env_info=False,
)

# build a top-down grasp pose for the TARGET cube (same method as PickCube)
obb = get_actor_obb(target)
approaching = np.array([0, 0, -1])
target_closing = base.agent.tcp.pose.to_transformation_matrix()[0, :3, 1].cpu().numpy()
grasp_info = compute_grasp_info_by_obb(
    obb, approaching=approaching, target_closing=target_closing, depth=FINGER_LENGTH,
)
grasp_pose = base.agent.build_grasp_pose(approaching, grasp_info["closing"], target.pose.sp.p)

frames = []
def cap():
    img = np.asarray(env.render())
    frames.append((img[0] if img.ndim == 4 else img).astype("uint8"))

cap()                                                   # 0 initial
planner.move_to_pose_with_screw(grasp_pose * sapien.Pose([0, 0, -0.05])); cap()  # 1 reach (above)
planner.move_to_pose_with_screw(grasp_pose);             cap()                    # 2 at cube
planner.close_gripper();                                 cap()                    # 3 grasp
planner.move_to_pose_with_screw(grasp_pose * sapien.Pose([0, 0, -0.12])); cap()  # 4 lift

is_grasped = bool(base.agent.is_grasping(target))
final_cube_z = float(target.pose.p[0, 2])
planner.close()
env.close()

grid = np.concatenate(frames, axis=1)
out = f"{PROJECT_ROOT}/data/custom/ThreeColoredCubes-v1/grasp_{TARGET}_seed{SEED}.png"
imageio.imwrite(out, grid)

print(f"TARGET={TARGET} SEED={SEED}")
print(f"is_grasped={is_grasped}")
print(f"cube_z: {init_cube_z:.4f} -> {final_cube_z:.4f}  (lifted {final_cube_z - init_cube_z:+.4f} m)")
print(f"SAVED: {out}")
