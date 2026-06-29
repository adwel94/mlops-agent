"""WSL-side Path-A 정직성 게이트: 기록된 **절대 EEF** 액션을 GR00T 롤아웃이 쓰는 것과
**똑같은 디코드 경로**(rot6d→quat → robot base 프레임 → mplib IK → step)로 모델 없이
open-loop 재생해, 기록 성공률이 재현되는지 확인한다.

목적: 평가의 "절대 EEF 실행 경로"가 정직한지(=버그로 모델을 억울하게 깎고 있지 않은지)를
모델·serve 없이 검증. ee_verify(_wsl_ee_verify.py)는 *델타* 경로를 게이트하지만, GR00T
롤아웃은 *절대 rot6d* 경로를 쓴다 — 이 스크립트가 바로 그 경로를 게이트한다.

재현율 ≈ 1.0 이면 디코드/프레임/IK 경로 결백 → 모델 실패는 진짜 모델 탓.
낮으면 → 평가 경로 자체에 버그 → 측정 artifact.

ik_exec(env+IK 배관)를 ee_verify·gr00t_eval 과 공유. WSL(mplib+llvmpipe)에서 구동.
"""
import argparse
import json
import random
import sys

PROJECT_ROOT = "/mnt/c/Users/hun41/PycharmProjects/maniskill"
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import h5py
from tqdm import tqdm

from scripts.ee_convert import episode_to_abs_eef, abs_eef_to_pose
from scripts.ik_exec import np1, make_env_and_solver, solve_to_arm


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--traj-path", required=True)
    p.add_argument("--count", type=int, default=0)   # 0 = all; else random sample
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--sim-backend", default="cpu")
    args = p.parse_args()

    sidecar = json.load(open(args.traj_path.replace(".h5", ".json")))
    eps_meta = sidecar.get("episodes", [])

    env, base, solver, base_p, base_q = make_env_and_solver(
        args.task, sim_backend=args.sim_backend, obs_mode="none",
    )

    f = h5py.File(args.traj_path, "r")
    keys = sorted(f.keys(), key=lambda k: int(k.split("_")[1]))
    if args.count and args.count < len(keys):
        keys = sorted(random.Random(args.seed).sample(keys, args.count),
                      key=lambda k: int(k.split("_")[1]))

    orig_succ = rep_succ = ik_fail_total = 0
    pbar = tqdm(keys)
    for k in keys:
        i = int(k.split("_")[1])
        ep = f[k]
        tcp = ep["obs"]["extra"]["tcp_pose"][:]            # (T,7)
        act = ep["actions"][:]                             # (T-1,A) joint (gripper = last dim)
        abs_eef = episode_to_abs_eef(tcp)                  # (T,9) absolute xyz+rot6d
        orig = bool(np.asarray(ep["success"])[-1])
        orig_succ += orig
        seed = eps_meta[i].get("episode_seed", i) if i < len(eps_meta) else i

        env.reset(seed=seed)
        last_q = np1(base.agent.robot.get_qpos())
        success = False
        n = act.shape[0]
        for t in range(n):
            # 모델이 출력했을 "다음 절대 pose" 자리에 기록값 abs_eef[t+1] 을 넣는다.
            # eval 과 동일하게: rot6d→quat(abs_eef_to_pose) → base 프레임 → IK → step.
            tp, tq = abs_eef_to_pose(abs_eef[t + 1])
            arm, failed = solve_to_arm(
                solver, np.asarray(tp, float), np.asarray(tq, float),
                base_p, base_q, last_q)
            ik_fail_total += int(failed)
            _o, _r, _term, _tr, info = env.step(np.hstack([arm, float(act[t][-1])]))
            last_q = np1(base.agent.robot.get_qpos())
            success = bool(np.asarray(info["success"]).reshape(-1)[0])
        rep_succ += int(success)
        pbar.update(1)
        pbar.set_postfix(dict(orig=orig_succ, rep=rep_succ))

    f.close()
    env.close()
    n = len(keys)
    rate = rep_succ / max(orig_succ, 1)
    print(f"DONE abs_eef_replay orig_success={orig_succ}/{n} replay_success={rep_succ}/{n} "
          f"reproduction_rate={rate:.3f} ik_fails={ik_fail_total}")


if __name__ == "__main__":
    main()
