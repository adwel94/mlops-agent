"""Convert recorded joint trajectories to a 7-DoF relative end-effector (EE-delta)
action representation, derived purely from the recorded `obs/extra/tcp_pose`.

EE action[t] (7d) = [dx, dy, dz, rx, ry, rz, gripper]
  - dx,dy,dz : world-frame translation delta   p[t+1] - p[t]
  - rx,ry,rz : axis-angle of the rotation delta q[t+1] * q[t]^-1  (world frame)
  - gripper  : recorded gripper command (last dim of the joint action), passthrough

This is a self-consistent convention we own on BOTH ends (Path B, no pinocchio):
  forward  (here):           pose[t], pose[t+1] -> ee[t]
  inverse  (execution/IK):   pose[t], ee[t]     -> target pose[t+1]  (then mplib IK)
The round-trip self-check below confirms inverse(forward) reproduces pose[t+1].

Pure numpy (quaternions are sapien/ManiSkill [w,x,y,z]); no scipy/pinocchio.

Functions:
  episode_joint_to_ee(tcp_pose, joint_actions) -> ee_actions (N,7)   # Path B: deltas
  ee_delta_to_target_pose(p_t, q_t, ee_row)    -> (target_p, target_q)   # for IK exec
  episode_to_abs_eef(tcp_pose)                 -> abs_eef (T,9)      # Path A: absolute xyz+rot6d
CLI:
  python scripts/ee_convert.py --traj-path <dataset.h5>          # self-check + stats
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# ---- quaternion helpers (w, x, y, z), vectorized over leading axes ----------

def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bw, bx, by, bz = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ], axis=-1)


def quat_conj(q: np.ndarray) -> np.ndarray:
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def quat_to_rotvec(q: np.ndarray) -> np.ndarray:
    """Unit quaternion -> axis-angle rotation vector (shortest; assumes w>=0 input)."""
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    w = np.clip(q[..., 0], -1.0, 1.0)
    xyz = q[..., 1:]
    sin_half = np.linalg.norm(xyz, axis=-1)
    angle = 2.0 * np.arctan2(sin_half, w)                 # w>=0 -> angle in [0, pi]
    small = sin_half < 1e-8
    denom = np.where(small, 1.0, sin_half)
    axis = xyz / denom[..., None]
    rotvec = axis * angle[..., None]
    return np.where(small[..., None], 2.0 * xyz, rotvec)  # small-angle: rotvec ~ 2*xyz


def rotvec_to_quat(rv: np.ndarray) -> np.ndarray:
    """Axis-angle rotation vector -> unit quaternion (w, x, y, z)."""
    angle = np.linalg.norm(rv, axis=-1, keepdims=True)    # (...,1)
    small = angle < 1e-8
    axis = rv / np.where(small, 1.0, angle)
    half = angle / 2.0
    q = np.concatenate([np.cos(half), axis * np.sin(half)], axis=-1)
    q_small = np.concatenate([np.ones_like(angle), rv / 2.0], axis=-1)
    q = np.where(small, q_small, q)
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def quat_angle_err(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Geodesic angle (rad) between two unit quaternions (sign-agnostic)."""
    qd = quat_mul(q1, quat_conj(q2))
    return 2.0 * np.arccos(np.clip(np.abs(qd[..., 0]), -1.0, 1.0))


# ---- conversion ------------------------------------------------------------

def episode_joint_to_ee(tcp_pose: np.ndarray, joint_actions: np.ndarray) -> np.ndarray:
    """tcp_pose (T,7) + joint_actions (T-1,A) -> ee_actions (T-1,7).

    tcp_pose rows are [px,py,pz, qw,qx,qy,qz]; gripper is the last dim of each
    joint action, passed through unchanged.
    """
    p = tcp_pose[:, :3]
    q = tcp_pose[:, 3:]
    dp = p[1:] - p[:-1]                                   # (T-1,3) world-frame
    q_delta = quat_mul(q[1:], quat_conj(q[:-1]))          # (T-1,4) q[t+1]*q[t]^-1
    flip = q_delta[:, 0] < 0                              # shortest rotation (w>=0)
    q_delta[flip] *= -1.0
    rotvec = quat_to_rotvec(q_delta)                      # (T-1,3)
    gripper = joint_actions[:, -1:]                       # (T-1,1) passthrough
    return np.concatenate([dp, rotvec, gripper], axis=1)  # (T-1,7)


def ee_delta_to_target_pose(p_t: np.ndarray, q_t: np.ndarray, ee_row: np.ndarray):
    """Inverse used at execution time: current pose + ee delta -> target pose.

    Returns (target_p (3,), target_q (4,)). mplib IK then solves joints for this.
    """
    target_p = p_t + ee_row[:3]
    target_q = quat_mul(rotvec_to_quat(ee_row[3:6]), q_t)
    return target_p, target_q


# ---- absolute EEF (xyz + rot6d), for GR00T-flavored LeRobot (Path A) -------

def quat_to_rot6d(q: np.ndarray) -> np.ndarray:
    """Unit quaternion(s) (w,x,y,z) -> 6D rotation = first two ROWS of the rotation
    matrix, flattened: [R00,R01,R02, R10,R11,R12].

    Matches GR00T's pose.py (`_matrix_to_rot6d` = `rotation_matrix[:2, :].flatten()`,
    rebuilt via Gram-Schmidt) so GR00T's RELATIVE/EEF relativization reads it correctly.
    Standard quaternion->matrix formula (same convention as scipy `Rotation.as_matrix`).
    """
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    w, x, y, z = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    r00 = 1 - 2 * (y * y + z * z); r01 = 2 * (x * y - w * z);   r02 = 2 * (x * z + w * y)
    r10 = 2 * (x * y + w * z);     r11 = 1 - 2 * (x * x + z * z); r12 = 2 * (y * z - w * x)
    return np.stack([r00, r01, r02, r10, r11, r12], axis=-1)


def episode_to_abs_eef(tcp_pose: np.ndarray) -> np.ndarray:
    """tcp_pose (T,7) [px,py,pz, qw,qx,qy,qz] -> absolute EEF (T,9) = xyz + rot6d.

    GR00T's XYZ_ROT6D end-effector format. Stored ABSOLUTE; GR00T's rep=RELATIVE +
    state_key computes the per-step relative motion internally (we do NOT pre-delta).
    """
    p = tcp_pose[:, :3].astype(np.float64)
    rot6d = quat_to_rot6d(tcp_pose[:, 3:].astype(np.float64))
    return np.concatenate([p, rot6d], axis=1)               # (T,9)


# ---- inverse rot6d -> quaternion (model output -> pose, for IK at eval time) ----

def rot6d_to_matrix(rot6d: np.ndarray) -> np.ndarray:
    """6D rotation (first two ROWS of R, flattened) -> rotation matrix (...,3,3).

    Gram-Schmidt reconstruction matching GR00T's pose.py: a1,a2 are the first two
    rows; orthonormalize to b1,b2 and b3 = b1 x b2. Inverse of quat_to_rot6d's layout.
    """
    a1 = rot6d[..., 0:3]
    a2 = rot6d[..., 3:6]
    b1 = a1 / np.linalg.norm(a1, axis=-1, keepdims=True)
    a2 = a2 - np.sum(b1 * a2, axis=-1, keepdims=True) * b1
    b2 = a2 / np.linalg.norm(a2, axis=-1, keepdims=True)
    b3 = np.cross(b1, b2)
    return np.stack([b1, b2, b3], axis=-2)                  # rows -> (...,3,3)


def matrix_to_quat(R: np.ndarray) -> np.ndarray:
    """Rotation matrix (...,3,3) -> unit quaternion (w,x,y,z), Shepperd's method.

    Same convention as quat_to_rot6d (scipy `Rotation.as_matrix`), vectorized over
    leading axes with a branchless 4-case select for numerical stability.
    """
    m00 = R[..., 0, 0]; m01 = R[..., 0, 1]; m02 = R[..., 0, 2]
    m10 = R[..., 1, 0]; m11 = R[..., 1, 1]; m12 = R[..., 1, 2]
    m20 = R[..., 2, 0]; m21 = R[..., 2, 1]; m22 = R[..., 2, 2]
    trace = m00 + m11 + m22

    def _q(S, w, x, y, z):
        return np.stack([w, x, y, z], axis=-1)

    St = np.sqrt(np.maximum(trace + 1.0, 1e-12)) * 2.0
    qt = _q(St, 0.25 * St, (m21 - m12) / St, (m02 - m20) / St, (m10 - m01) / St)
    S0 = np.sqrt(np.maximum(1.0 + m00 - m11 - m22, 1e-12)) * 2.0
    q0 = _q(S0, (m21 - m12) / S0, 0.25 * S0, (m01 + m10) / S0, (m02 + m20) / S0)
    S1 = np.sqrt(np.maximum(1.0 + m11 - m00 - m22, 1e-12)) * 2.0
    q1 = _q(S1, (m02 - m20) / S1, (m01 + m10) / S1, 0.25 * S1, (m12 + m21) / S1)
    S2 = np.sqrt(np.maximum(1.0 + m22 - m00 - m11, 1e-12)) * 2.0
    q2 = _q(S2, (m10 - m01) / S2, (m02 + m20) / S2, (m12 + m21) / S2, 0.25 * S2)

    cond_t = (trace > 0)[..., None]
    cond0 = ((m00 >= m11) & (m00 >= m22))[..., None]
    cond1 = (m11 >= m22)[..., None]
    q = np.where(cond_t, qt, np.where(cond0, q0, np.where(cond1, q1, q2)))
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def rot6d_to_quat(rot6d: np.ndarray) -> np.ndarray:
    """6D rotation -> unit quaternion (w,x,y,z). Inverse of quat_to_rot6d."""
    return matrix_to_quat(rot6d_to_matrix(rot6d))


def abs_eef_to_pose(eef9: np.ndarray):
    """Absolute EEF row(s) (...,9)=[xyz, rot6d] -> (p (...,3), q (...,4)) world pose.

    Used at eval time to turn a GR00T-predicted absolute EEF action into a target
    pose for mplib IK.
    """
    return eef9[..., :3], rot6d_to_quat(eef9[..., 3:9])


# ---- self-check over a dataset --------------------------------------------

def run(traj_path: str | Path, check: bool = True) -> dict:
    """Convert every episode and (optionally) round-trip self-check. Returns stats."""
    import h5py

    traj_path = Path(traj_path)
    max_perr = max_rerr = max_r6err = 0.0
    total = 0
    dp_abs = []
    rot_mag = []
    with h5py.File(traj_path, "r") as f:
        keys = sorted(f.keys(), key=lambda k: int(k.split("_")[1]))
        for k in keys:
            ep = f[k]
            tcp = ep["obs"]["extra"]["tcp_pose"][:]
            act = ep["actions"][:]
            ee = episode_joint_to_ee(tcp, act)
            total += ee.shape[0]
            dp_abs.append(np.abs(ee[:, :3]))
            rot_mag.append(np.linalg.norm(ee[:, 3:6], axis=-1))
            if check:
                p0, q0 = tcp[:-1, :3], tcp[:-1, 3:]
                tp = p0 + ee[:, :3]
                tq = quat_mul(rotvec_to_quat(ee[:, 3:6]), q0)
                max_perr = max(max_perr, float(np.linalg.norm(tp - tcp[1:, :3], axis=-1).max()))
                max_rerr = max(max_rerr, float(quat_angle_err(tq, tcp[1:, 3:]).max()))
                # rot6d round-trip (Path A: abs-EEF store -> eval-time IK target)
                q_rt = rot6d_to_quat(quat_to_rot6d(tcp[:, 3:]))
                max_r6err = max(max_r6err, float(quat_angle_err(q_rt, tcp[:, 3:]).max()))

    dp_abs = np.concatenate(dp_abs)
    rot_mag = np.concatenate(rot_mag)
    stats = {
        "episodes": len(keys), "steps": total,
        "recon_pos_err_m": max_perr, "recon_rot_err_deg": float(np.degrees(max_rerr)),
        "rot6d_roundtrip_err_deg": float(np.degrees(max_r6err)),
        "dpos_max_m": float(dp_abs.max()), "dpos_mean_m": float(dp_abs.mean()),
        "drot_max_deg": float(np.degrees(rot_mag.max())),
        "drot_mean_deg": float(np.degrees(rot_mag.mean())),
    }
    if check:
        print(f"[ee_convert] episodes={stats['episodes']} steps={stats['steps']}")
        print(f"[ee_convert] round-trip recon  pos err max = {stats['recon_pos_err_m']:.2e} m  "
              f"|  rot err max = {stats['recon_rot_err_deg']:.2e} deg   (should be ~0)")
        print(f"[ee_convert] rot6d<->quat round-trip rot err max = "
              f"{stats['rot6d_roundtrip_err_deg']:.2e} deg   (should be ~0)")
        print(f"[ee_convert] per-step |Δpos|  max={stats['dpos_max_m']:.4f}  mean={stats['dpos_mean_m']:.4f} m")
        print(f"[ee_convert] per-step |Δrot|  max={stats['drot_max_deg']:.2f}  mean={stats['drot_mean_deg']:.2f} deg")
    return stats


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--traj-path", required=True)
    p.add_argument("--no-check", action="store_true", help="skip round-trip self-check")
    args = p.parse_args()
    run(args.traj_path, check=not args.no_check)


if __name__ == "__main__":
    _cli()
