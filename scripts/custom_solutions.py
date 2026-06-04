"""Motion-planning solutions for this harness's custom environments.

WSL-only: these import ManiSkill's mplib-based motion planner, so they run inside
the WSL conda env (reached over /mnt/c), never on Windows. Each solution takes the
(RecordEpisode-wrapped) env + a seed, runs the recipe via the planner, and returns
the final env step result `(obs, reward, terminated, truncated, info)` so the
caller can read `info["success"]` — matching ManiSkill's run.py contract.
"""
import numpy as np
import sapien

from mani_skill.examples.motionplanning.panda.motionplanner import (
    PandaArmMotionPlanningSolver,
)
from mani_skill.examples.motionplanning.base_motionplanner.utils import (
    compute_grasp_info_by_obb, get_actor_obb,
)

FINGER_LENGTH = 0.025


def solve_three_colored_cubes(env, seed=None, debug=False, vis=False):
    """Pick the env-chosen target cube (env.target_id) and lift it.

    The target is decided by the env from the seed, so this solution just reads
    it — same seed always grasps the same cube.
    """
    env.reset(seed=seed)
    base = env.unwrapped
    planner = PandaArmMotionPlanningSolver(
        env, debug=debug, vis=vis,
        base_pose=base.agent.robot.pose,
        visualize_target_grasp_pose=vis, print_env_info=False,
    )

    target = base.cubes[int(base.target_id[0])]
    obb = get_actor_obb(target)
    approaching = np.array([0, 0, -1])
    target_closing = base.agent.tcp.pose.to_transformation_matrix()[0, :3, 1].cpu().numpy()
    grasp_info = compute_grasp_info_by_obb(
        obb, approaching=approaching, target_closing=target_closing, depth=FINGER_LENGTH,
    )
    grasp_pose = base.agent.build_grasp_pose(approaching, grasp_info["closing"], target.pose.sp.p)

    planner.move_to_pose_with_screw(grasp_pose * sapien.Pose([0, 0, -0.05]))  # reach above
    planner.move_to_pose_with_screw(grasp_pose)                              # descend
    planner.close_gripper()                                                  # grasp
    res = planner.move_to_pose_with_screw(grasp_pose * sapien.Pose([0, 0, -0.12]))  # lift
    planner.close()
    return res


# task id -> solution fn (so the generator and dispatcher can look it up)
SOLUTIONS = {
    "ThreeColoredCubes-v1": solve_three_colored_cubes,
}
