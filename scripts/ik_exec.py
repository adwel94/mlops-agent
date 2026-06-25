"""Shared mplib-IK execution helpers (WSL / Linux only — needs mplib + sapien).

The common ground between the two EE rollout executors:
  - scripts/_wsl_ee_verify.py   replays recorded EE-deltas (method gate)
  - scripts/_wsl_gr00t_eval.py  rolls out a GR00T policy's absolute-EEF actions

Both need the same plumbing: build the env + Panda motion-planning solver, transform
a world-frame target pose into the robot base frame (mplib IK expects base frame),
solve joints via planner.IK, and pick the branch closest to the current arm config.
Pure inverse-kinematics glue — no torch. (mplib is Linux-only, hence WSL.)
"""
import numpy as np

# WSL has only the llvmpipe software renderer; let sapien auto-select it when the
# explicit 'cpu' device is rejected (same fix as the solve wrappers / ee_verify).
import sapien.render as _R
_orig_rs = _R.RenderSystem
def _safe_rs(*a, **k):
    try:
        return _orig_rs(*a, **k)
    except RuntimeError:
        return _orig_rs()
_R.RenderSystem = _safe_rs

import gymnasium as gym
import mani_skill.envs  # noqa: F401
import scripts.custom_envs  # noqa: F401  (registers custom tasks)
from mani_skill.examples.motionplanning.panda.motionplanner import (
    PandaArmMotionPlanningSolver,
)
from scripts.ee_convert import quat_mul, quat_conj


def np1(x):
    """Tensor/array (maybe batched, num_envs=1) -> 1d numpy vector."""
    a = np.asarray(x.cpu().numpy() if hasattr(x, "cpu") else x)
    return a.reshape(-1) if a.ndim == 1 else a[0]


def _quat_rotate(q, v):
    """Rotate 3-vector v by quaternion q (w,x,y,z)."""
    qv = np.concatenate([[0.0], v])
    return quat_mul(quat_mul(q, qv), quat_conj(q))[1:]


def world_to_base(p_w, q_w, base_p, base_q):
    """World-frame pose -> robot-base frame (mplib IK expects the goal in base frame)."""
    bq_inv = quat_conj(base_q)
    return _quat_rotate(bq_inv, p_w - base_p), quat_mul(bq_inv, q_w)


def pick_ik(qsol, ref7):
    """Choose the IK solution whose arm joints are closest to ref7. Returns (7,) or None."""
    if qsol is None:
        return None
    arr = np.asarray(qsol, dtype=float)
    if arr.size == 0:
        return None
    if arr.ndim == 1:
        return arr[:7]
    j = int(np.argmin(np.linalg.norm(arr[:, :7] - ref7, axis=1)))
    return arr[j, :7]


def make_env_and_solver(task, sim_backend="cpu", obs_mode="none"):
    """Build the env + Panda IK solver. Returns (env, base, solver, base_p, base_q).

    base_p/base_q = robot base pose in world (constant; the IK goal is expressed
    relative to it via world_to_base).
    """
    env = gym.make(
        task, obs_mode=obs_mode, control_mode="pd_joint_pos",
        render_mode="rgb_array", sim_backend=sim_backend,
        render_backend="cpu", reward_mode="none",
    )
    base = env.unwrapped
    env.reset(seed=0)
    solver = PandaArmMotionPlanningSolver(
        env, vis=False, base_pose=base.agent.robot.pose, print_env_info=False,
    )
    base_p = np1(base.agent.robot.pose.p)
    base_q = np1(base.agent.robot.pose.q)
    return env, base, solver, base_p, base_q


def solve_to_arm(solver, target_p_world, target_q_world, base_p, base_q, ref_q):
    """World-frame target pose -> 7 arm joints via mplib IK. Returns (arm7, ik_failed).

    ref_q = current full qpos (IK seed + closest-branch reference). On IK failure
    returns (ref_q[:7], True) so the caller can hold the last joints.
    """
    gp, gq = world_to_base(target_p_world, target_q_world, base_p, base_q)
    goal = np.concatenate([gp, gq])
    status, qsol = solver.planner.IK(goal, ref_q)
    arm = pick_ik(qsol, ref_q[:7]) if status == "Success" else None
    if arm is None:
        return ref_q[:7], True
    return arm, False
