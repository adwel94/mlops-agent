"""커스텀 task 가 하네스의 계약을 지키는지 코드로 검증 (add_custom_task 스킬의 게이트).

태스크가 "가능하냐"는 고맥락 판단이라 코드가 아니라 사람/AI 가 자연어 가이드라인으로
정한다(`.claude/skills/add_custom_task`). 이 스크립트는 그 판단의 **결과물**이 확실한
계약을 지키는지만 본다 — 즉 "이 태스크를 ②③④ 파이프라인에 흘려도 되는가".

검증 = 두 층:

  [static]  (Windows CPU sim, WSL 불필요)
    - env 가 등록됐나 / CUSTOM_TASKS·SOLUTIONS 에 있나
    - 주 카메라(첫 sensor)가 `base_camera` 인가      (h5_to_lerobot·modality 계약)
    - obs/extra 에 `tcp_pose` 가 있나                  (④ EE 분기의 생명줄)
    - evaluate() 가 `success` 키를 내나                (성공 판정 계약)

  [dynamic] (WSL — mplib)  : --static-only 로 생략 가능
    - task_to_h5(count) → h5_add_images(count) → ee_verify(count)
    - 즉 실제 파이프라인을 작은 규모로 흘려, 솔루션이 **실제로 풀고**(orig success>0)
      그 EE 모션이 **역기구학으로 재현되는지**(reproduction_rate, ik_fails) 확인.

성공 기준은 우리가 발명하지 않는다 — 태스크의 `evaluate().success` 가 ground truth.

  - Python:  from scripts.validate_custom_task import run; run("ThreeColoredCubes-v1")
  - CLI:     python scripts/validate_custom_task.py ThreeColoredCubes-v1 [--static-only] [--count 3]
"""
from __future__ import annotations

import os
import sys
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.h5_to_lerobot import BASE_CAMERA as CAMERA_CONTRACT  # 단일 출처 (위치 무관, 이름으로 계약)


class _Check:
    """한 계약 검사의 결과 (이름, 통과 여부, 상세)."""

    def __init__(self, name: str, ok: bool, detail: str = ""):
        self.name, self.ok, self.detail = name, ok, detail

    def line(self) -> str:
        mark = "OK  " if self.ok else "FAIL"
        return f"  [{mark}] {self.name}" + (f"  — {self.detail}" if self.detail else "")


def _solutions_has(task: str) -> bool:
    """custom_solutions.SOLUTIONS 에 task 가 키로 등록됐는지 — 소스 텍스트로 확인.
    (custom_solutions 는 mplib[Linux 전용]을 import 해 Windows 에서 import 불가 → 텍스트 검사.
     실제 솔루션 실행 검증은 동적 단계의 task_to_h5(WSL)가 한다.)"""
    import re
    src = os.path.join(_ROOT, "scripts", "custom_solutions.py")
    try:
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    return re.search(rf"""["']{re.escape(task)}["']\s*:""", text) is not None


def _static(task: str, seed: int, sim_backend: str) -> list[_Check]:
    """WSL 없이 Windows CPU sim 으로 확실한 계약만 검사."""
    import gymnasium as gym
    import scripts.custom_envs  # noqa: F401  (registers custom tasks; mplib 없이 import 가능)
    from scripts.task_to_h5 import CUSTOM_TASKS

    checks: list[_Check] = []
    checks.append(_Check("CUSTOM_TASKS 등록", task in CUSTOM_TASKS,
                         "" if task in CUSTOM_TASKS else f"{task} 를 task_to_h5.CUSTOM_TASKS 에 추가 필요"))
    has_sol = _solutions_has(task)
    checks.append(_Check("SOLUTIONS 등록 (소스)", has_sol,
                         "" if has_sol else f"{task} 솔루션을 custom_solutions.SOLUTIONS 에 등록 필요"))

    # 환경을 실제로 띄워 obs/evaluate 계약을 본다 (render_backend='cpu' — Windows GPU 렌더 불가).
    env = None
    try:
        env = gym.make(task, obs_mode="rgb", sim_backend=sim_backend,
                       render_backend="cpu", num_envs=1)
        obs, _info = env.reset(seed=seed)

        sensors = list(obs.get("sensor_data", {}).keys())
        # h5_to_lerobot 은 카메라를 **이름**(base_camera)으로 집어간다 → 위치 무관,
        # 그 이름이 **존재**하기만 하면 됨 (new_embodiment_config 와 일치).
        has_cam = CAMERA_CONTRACT in sensors
        checks.append(_Check(
            f"카메라 {CAMERA_CONTRACT!r} 존재", has_cam,
            f"sensors={sensors}" + ("" if has_cam else
                f" — 주 카메라 이름이 {CAMERA_CONTRACT} 여야 학습/서빙 modality 일치")))

        extra = obs.get("extra", {})
        has_tcp = "tcp_pose" in extra
        checks.append(_Check(
            "obs/extra/tcp_pose 존재", has_tcp,
            "" if has_tcp else f"_get_obs_extra 가 tcp_pose 를 내야 ④ EE 분기 동작 (현재 키: {list(extra.keys())})"))

        succ = env.unwrapped.evaluate()
        has_succ = isinstance(succ, dict) and "success" in succ
        checks.append(_Check(
            "evaluate().success 존재", has_succ,
            "" if has_succ else f"evaluate() 가 'success' 키를 내야 함 (현재: {list(succ) if isinstance(succ, dict) else type(succ)})"))

        # 언어 명령 틀 계약 — 학습(h5_to_lerobot)·평가(gr00t_eval)가 이 하나에서 읽어 문구
        # 어긋남을 막는 단일 출처. {placeholder} 는 label_metadata 키로 채워져야(채움 실패 시
        # 조용한 fallback → 학습≠평가). placeholder 없는 고정 문구도 허용(빈 집합 ⊆ 어떤 집합).
        import string as _string
        tmpl = env.unwrapped.instruction_template() if hasattr(env.unwrapped, "instruction_template") else None
        ph = {f for _, f, _, _ in _string.Formatter().parse(tmpl) if f} if isinstance(tmpl, str) else set()
        label_keys = set((env.unwrapped.label_metadata() or {}).keys()) if hasattr(env.unwrapped, "label_metadata") else set()
        instr_ok = isinstance(tmpl, str) and bool(tmpl) and ph <= label_keys
        checks.append(_Check(
            "instruction_template() 존재·채움가능", instr_ok,
            "" if instr_ok else
            f"instruction_template() 가 문자열 틀을 내야 함(학습/평가 단일 출처). "
            f"현재={tmpl!r}, placeholder={ph}, label_metadata 키={label_keys} — placeholder 는 그 키의 부분집합이어야 채워짐"))
    except Exception as e:
        checks.append(_Check("환경 인스턴스화", False,
                             f"{type(e).__name__}: {e}\n{traceback.format_exc()}"))
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
    return checks


# 검증은 **scratch 이름**에 쓴다 — 실제 motionplanning.h5 를 덮어쓰면 기존 task 데이터를
# 파괴하므로(새 task 엔 무해하지만 재검증 시 치명적). 끝나면 정리.
SCRATCH_NAME = "_validate_scratch"


def _dynamic(task: str, count: int, seed: int, sim_backend: str,
             min_reproduction: float, keep_artifacts: bool) -> tuple[list[_Check], dict]:
    """실제 파이프라인을 count 규모로 흘려 솔루션 성공 + EE/IK 재현을 확인 (WSL)."""
    from scripts import task_to_h5, h5_add_images, ee_verify

    checks: list[_Check] = []
    info: dict = {}
    scratch: list = []   # 정리할 파일 모음

    try:
        # ① 솔루션으로 궤적 생성 (WSL 모션플래닝). only_success=False → 실제 성공률 측정 가능.
        #    traj_name=SCRATCH → 실제 motionplanning.h5 를 안 건드림.
        traj = task_to_h5.run(task, count=count, traj_name=SCRATCH_NAME,
                              only_success=False, sim_backend=sim_backend)
        scratch += [traj, traj.with_suffix(".json")]
        checks.append(_Check("task_to_h5 (솔루션 실행)", traj.exists(),
                             f"-> {traj.name}" if traj.exists() else "궤적 .h5 미생성"))
        if not traj.exists():
            return checks, info

        # ② 리플레이로 이미지+tcp_pose 입힌 데이터셋 (Windows CPU sim).
        dataset = h5_add_images.run(task, count=count, traj_path=traj)
        scratch += [dataset, dataset.with_suffix(".json")]
        checks.append(_Check("h5_add_images (데이터셋)", dataset.exists(),
                             f"-> {dataset.name}" if dataset.exists() else "데이터셋 .h5 미생성"))
        if not dataset.exists():
            return checks, info

        # ③ EE 델타 → mplib IK 재현 게이트 (WSL). orig/ee success, reproduction_rate, ik_fails.
        res = ee_verify.run(dataset, count=count, seed=seed, sim_backend=sim_backend)
        info = res
    finally:
        if not keep_artifacts:
            for p in scratch:
                try:
                    p.unlink()
                except OSError:
                    pass
    orig = _num(res.get("orig_success", "0/0"))   # (성공, 전체)
    rate = float(res.get("reproduction_rate", 0.0) or 0.0)
    ik_fails = int(res.get("ik_fails", 0) or 0)

    checks.append(_Check("솔루션이 실제로 푼다 (orig success>0)", orig[0] > 0,
                         f"orig_success={res.get('orig_success')}"))
    checks.append(_Check(f"EE 역기구학 재현 (rate≥{min_reproduction})", rate >= min_reproduction,
                         f"reproduction_rate={rate:.3f} ee_success={res.get('ee_success')}"))
    checks.append(_Check("IK 안정 (ik_fails 낮음)", ik_fails == 0,
                         f"ik_fails={ik_fails}" + ("" if ik_fails == 0 else " (>0 이면 EE 목표가 IK 로 안 풀림)")))
    return checks, info


def _num(frac: str) -> tuple[int, int]:
    """'8/10' -> (8, 10)."""
    try:
        a, b = str(frac).split("/")
        return int(a), int(b)
    except Exception:
        return 0, 0


def run(
    task: str,
    count: int = 3,
    seed: int = 0,
    sim_backend: str = "cpu",
    static_only: bool = False,
    min_reproduction: float = 0.8,
    keep_artifacts: bool = False,
) -> dict:
    """커스텀 task 의 계약을 검증하고 {passed, static, dynamic, ee} 를 반환."""
    print(f"== validate_custom_task: {task} (count={count}, static_only={static_only}) ==\n")

    static = _static(task, seed, sim_backend)
    print("[static]  (Windows CPU sim)")
    for c in static:
        print(c.line())
    static_ok = all(c.ok for c in static)

    dynamic: list[_Check] = []
    ee: dict = {}
    if static_only:
        print("\n[dynamic] 생략 (--static-only)")
    elif not static_ok:
        print("\n[dynamic] 생략 — static 실패 (계약부터 고치고 재검증)")
    else:
        print("\n[dynamic] (WSL — 실제 파이프라인 흘리기)")
        try:
            dynamic, ee = _dynamic(task, count, seed, sim_backend, min_reproduction, keep_artifacts)
        except Exception as e:
            dynamic = [_Check("동적 검증 실행", False, f"{type(e).__name__}: {e}")]
        for c in dynamic:
            print(c.line())

    dynamic_ok = all(c.ok for c in dynamic) if dynamic else (static_only or not static_ok)
    # static_only 면 동적 미실행이므로 동적 통과 여부는 'N/A'. 전체 통과는 실행한 층 기준.
    passed = static_ok and (static_only or dynamic_ok)

    print("\n== 결과 ==")
    print(f"  static : {'PASS' if static_ok else 'FAIL'}")
    if not static_only:
        print(f"  dynamic: {'PASS' if dynamic_ok else 'FAIL'}" if static_ok else "  dynamic: (미실행)")
    verdict = "PASS — 파이프라인에 사용 가능" if passed else "FAIL — 위 FAIL 항목을 고쳐야 함"
    print(f"  => {verdict}")

    return {"passed": passed, "static_ok": static_ok, "dynamic_ok": dynamic_ok if not static_only else None,
            "static": [(c.name, c.ok, c.detail) for c in static],
            "dynamic": [(c.name, c.ok, c.detail) for c in dynamic], "ee": ee}


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("task", help="커스텀 task id (예: ThreeColoredCubes-v1)")
    p.add_argument("--count", type=int, default=3, help="동적 검증 에피소드 수 (기본 3)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--sim-backend", default="cpu")
    p.add_argument("--static-only", action="store_true", help="WSL 동적 검증 생략 (계약만)")
    p.add_argument("--min-reproduction", type=float, default=0.8,
                   help="EE 재현율 통과 임계 (기본 0.8)")
    p.add_argument("--keep-artifacts", action="store_true",
                   help="검증 scratch 파일을 지우지 않고 남김 (기본: 정리)")
    args = p.parse_args()
    res = run(args.task, count=args.count, seed=args.seed, sim_backend=args.sim_backend,
              static_only=args.static_only, min_reproduction=args.min_reproduction,
              keep_artifacts=args.keep_artifacts)
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    _cli()
