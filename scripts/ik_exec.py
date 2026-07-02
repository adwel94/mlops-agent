"""Shared IK execution helpers (Linux: mplib · macOS: pinocchio).

The common ground between the two EE rollout executors:
  - scripts/_wsl_ee_verify.py   replays recorded EE-deltas (method gate)
  - scripts/_wsl_gr00t_eval.py  rolls out a GR00T policy's absolute-EEF actions

Both need the same plumbing: build the env + an IK solver, transform a world-frame
target pose into the robot base frame (the IK goal is base-frame), solve joints, and
pick the branch closest to the current arm config. Pure inverse-kinematics glue — no
torch. The IK backend is picked by availability: mplib (Linux 전용 바이너리, WSL 경로)
가 있으면 그대로, 없으면 pinocchio damped-least-squares IK (macOS 네이티브 경로).
둘 다 같은 URDF·같은 move-group(panda_hand_tcp)·같은 base-frame 목표를 풀므로
solve_to_arm 밖의 파이프라인은 백엔드와 무관하게 동일하다.
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
from scripts.ee_convert import quat_mul, quat_conj

# IK 백엔드는 가용성으로 선택 — mplib 이 import 되면(WSL/Linux) 기존 모션플래닝 솔버,
# 아니면(macOS) pinocchio. 여기서 실패해도 죽이지 않고 make_env_and_solver 에서 판정한다.
try:
    from mani_skill.examples.motionplanning.panda.motionplanner import (
        PandaArmMotionPlanningSolver,
    )
    _HAS_MPLIB = True
except ImportError:
    _HAS_MPLIB = False


def np1(x):
    """Tensor/array (maybe batched, num_envs=1) -> 1d numpy vector."""
    a = np.asarray(x.cpu().numpy() if hasattr(x, "cpu") else x)
    return a.reshape(-1) if a.ndim == 1 else a[0]


def _quat_rotate(q, v):
    """Rotate 3-vector v by quaternion q (w,x,y,z)."""
    qv = np.concatenate([[0.0], v])
    return quat_mul(quat_mul(q, qv), quat_conj(q))[1:]


def world_to_base(p_w, q_w, base_p, base_q):
    """World-frame pose -> robot-base frame (the IK goal is expressed in base frame)."""
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


class PinocchioIK:
    """pinocchio damped-least-squares IK — mplib planner.IK 의 드롭인 대체 (macOS).

    solve_to_arm 이 쓰는 계약을 그대로 따른다: goal = move-group 프레임(panda_hand_tcp)의
    로봇 base 프레임 7d pose [xyz, wxyz], 시드 ref_q(전체 qpos), 반환 (status, qsol).
    eval/verify 의 목표는 매 스텝 시드 근처로만 움직이므로 시드에서 시작한 DLS 몇 iter 로
    수렴하고, 그 자체로 시드에 가장 가까운 분기를 고른다(mplib+pick_ik 와 같은 효과).
    손가락(prismatic 2dof)은 IK 변수에서 제외 — 시드값에 고정.
    """
    MOVE_GROUP = "panda_hand_tcp"   # mplib PandaArmMotionPlanningSolver 와 동일 프레임
    ARM_DOF = 7

    def __init__(self, urdf_path):
        import pinocchio as pin
        self._pin = pin
        self.model = pin.buildModelFromUrdf(urdf_path)
        self.data = self.model.createData()
        self.fid = self.model.getFrameId(self.MOVE_GROUP)
        if self.fid >= self.model.nframes:
            raise ValueError(f"URDF has no frame '{self.MOVE_GROUP}': {urdf_path}")
        self.lo = np.asarray(self.model.lowerPositionLimit)
        self.hi = np.asarray(self.model.upperPositionLimit)

    @property
    def planner(self):
        return self     # solve_to_arm 는 solver.planner.IK(...) 를 부른다

    def IK(self, goal, ref_q, max_iters=100, tol=1e-4, damping=1e-8):
        pin = self._pin
        n = self.ARM_DOF
        p = np.asarray(goal[:3], dtype=float)
        w, x, y, z = np.asarray(goal[3:7], dtype=float)
        target = pin.SE3(pin.Quaternion(w, x, y, z).matrix(), p)
        q = np.array(ref_q, dtype=float).copy()
        for _ in range(max_iters):
            pin.framesForwardKinematics(self.model, self.data, q)
            fMd = self.data.oMf[self.fid].actInv(target)
            err = pin.log(fMd).vector           # 6d, 현재 프레임 좌표
            if np.linalg.norm(err) < tol:
                return "Success", q[None, :].copy()
            J = pin.computeFrameJacobian(
                self.model, self.data, q, self.fid, pin.ReferenceFrame.LOCAL)[:, :n]
            J = -(pin.Jlog6(fMd.inverse()) @ J)  # 공식 IK 예제와 동일한 오차 선형화
            dq = -J.T @ np.linalg.solve(J @ J.T + damping * np.eye(6), err)
            q[:n] = np.clip(q[:n] + dq, self.lo[:n], self.hi[:n])
        return "IK Failed", None


def make_env_and_solver(task, sim_backend="cpu", obs_mode="none", robot_uids="panda",
                        render_mode="rgb_array"):
    """Build the env + Panda IK solver. Returns (env, base, solver, base_p, base_q).

    base_p/base_q = robot base pose in world (constant; the IK goal is expressed
    relative to it via world_to_base).

    robot_uids selects the agent: "panda" (default, 1-cam) or "panda_wristcam" (adds a
    hand_camera). Same arm kinematics either way, so the IK solver (built from the
    agent's URDF) is unaffected; only the sensor set changes.

    render_mode: "rgb_array" (headless — eval/verify) or "human" (desktop viewer —
    gr00t_play).
    """
    env = gym.make(
        task, obs_mode=obs_mode, control_mode="pd_joint_pos",
        render_mode=render_mode, sim_backend=sim_backend,
        render_backend="cpu", reward_mode="none", robot_uids=robot_uids,
    )
    base = env.unwrapped
    env.reset(seed=0)
    if _HAS_MPLIB:
        solver = PandaArmMotionPlanningSolver(
            env, vis=False, base_pose=base.agent.robot.pose, print_env_info=False,
        )
    else:
        try:
            solver = PinocchioIK(base.agent.urdf_path)
        except ImportError:
            raise RuntimeError(
                "No IK backend: mplib (Linux) 도 pinocchio (macOS: conda install -c "
                "conda-forge pinocchio) 도 import 되지 않음 — SETUP.md 참고."
            )
    base_p = np1(base.agent.robot.pose.p)
    base_q = np1(base.agent.robot.pose.q)
    return env, base, solver, base_p, base_q


def solve_to_arm(solver, target_p_world, target_q_world, base_p, base_q, ref_q):
    """World-frame target pose -> 7 arm joints via IK. Returns (arm7, ik_failed).

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
