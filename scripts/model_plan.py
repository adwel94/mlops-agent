"""model_plan — 모델 개발 계획(YAML) 생성 + 반복 루프 판정.

두 입구 (CLAUDE.md 교차규칙 2: 스크립트가 원천, 스킬은 얇은 래퍼):
  - 함수:  run_create(...) / decide_logic(...)  — 다른 코드가 import 해 조합
  - CLI:   python scripts/model_plan.py create ...   (plan_create 스킬이 호출)
           python scripts/model_plan.py decide ...   (plan_run 스킬이 매 반복 호출)

역할 분담:
  - `create` = 결정론적 템플릿 채우기 + 검증. plan_create 스킬이 자연어를 플래그로 옮겨 부른다.
  - `decide` = 반복 루프의 **숫자 판정**(gap_fraction 산수)을 결정론으로 낸다. plan_run 스킬(AI)이
    매 평가 후 이걸 불러 "다음에 무엇을" 위임한다 — AI 가 눈대중으로 문턱을 정하지 않게.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLANS_DIR = PROJECT_ROOT / "plans"

# ── 기본값 (지금까지 합의한 것 — plan_create 가 오버라이드 없으면 이대로) ──────────
DEFAULTS = {
    "name": "my-model-plan",
    "task_kind": "existing",          # existing | custom
    "env_id": "ThreeColoredCubes-v1",
    "description": "",                 # custom 일 때 자연어
    "target": 0.90,
    "episodes": 50,
    "seed": 0,
    "holdout_start_seed": 90000,       # 홀드아웃 평가셋 씬 seed 시작점 (학습셋과 분리)
    "data_source": "task_to_h5",       # task_to_h5 | fetch_sample_h5
    "data_episodes": 100,
    "hf_dataset_repo": "adwel94/maniskill-threecubes-lerobot",
    "version": "v2",
    "hf_output_repo": "adwel94/maniskill-threecubes-gr00t",
    "finetune_scope": "head_only",     # head_only | full
    "ladder": [3000, 6000, 12000],
    "continue_type": "gap_fraction",   # gap_fraction | fixed_points
    "gap_fraction": 0.333,
    "fixed_points": 5,
    "confirm_on_ambiguous": True,
    "approval_mode": "per_pod",        # per_pod | pre_approved
}

_ENUMS = {
    "task_kind": {"existing", "custom"},
    "data_source": {"task_to_h5", "fetch_sample_h5"},
    "finetune_scope": {"head_only", "full"},
    "continue_type": {"gap_fraction", "fixed_points"},
    "approval_mode": {"per_pod", "pre_approved"},
}

# 템플릿에서 숨긴 필드의 기본값 (계획서에 없으면 decide 가 이 값 사용)
DEFAULT_STEP_LADDER = [3000, 6000, 12000]
DEFAULT_CONTINUE_RULE = {"type": "gap_fraction", "gap_fraction": 0.333, "fixed_points": 5}

# ── YAML 템플릿 (단일 출처 — plans/model_plan.template.yaml 은 이걸로 생성됨) ──────
TEMPLATE = """\
# 모델 개발 계획 — 정하는 것만.   [model_plan.py create 로 생성]
# ─────────────────────────────────────────────────────────────
# /plan_run 이 이 사양대로 [태스크→데이터→학습→평가→판정] 루프를 목표까지 반복한다.
# 여기 없는 값(평가 조건·손절 규칙·승인 방식 등)은 하네스 기본값으로 자동 적용된다.
# 특정 기본값을 바꾸려면 그 줄만 손으로 추가하면 오버라이드된다.

mission:
  name: {name}
  task:
    kind: {task_kind}                  # existing | custom
    env_id: {env_id}                   # kind=existing 일 때 (지원목록은 /task_to_h5)
    description: "{description}"        # kind=custom 일 때 자연어 (예: "빨간 공을 그릇에")
  # 언어 명령(instruction)은 환경(custom_envs.instruction_template)이 선언 — 학습·평가가 거기서
  # 읽으므로 계획서엔 두지 않는다(문구 단일 출처, 어긋남 방지).

goal:
  target_success_rate: {target}        # 이 점수 넘으면 완료

data:
  episodes: {data_episodes}            # 학습 데이터 몇 개
  hf_dataset_repo: {hf_dataset_repo}
  dataset_tag: {version}               # 데이터셋 스냅샷 태그 (불변; 바뀌면 새 태그)

training:
  hf_output_repo: {hf_output_repo}     # 학습된 모델 올릴 HF repo

loop:
  step_ladder: {ladder}                # 학습 스텝을 낮은 것부터 점진 (목표 도달까지 오름)
"""


# ── create ────────────────────────────────────────────────────────────────────
def _validate_create(v: dict) -> None:
    """생성 값 검증 — 잘못된 사양을 애초에 못 만들게 (create 실패가 곧 방어선)."""
    errs = []
    for key, allowed in _ENUMS.items():
        if v[key] not in allowed:
            errs.append(f"{key}={v[key]!r} 는 {sorted(allowed)} 중 하나여야 함")
    if not (0.0 < float(v["target"]) <= 1.0):
        errs.append(f"target={v['target']} 는 (0, 1] 범위여야 함 (성공률=분수)")
    if int(v["episodes"]) <= 0:
        errs.append("episodes 는 양수")
    if int(v["seed"]) < 0:
        errs.append("seed 는 0 이상")
    if int(v["data_episodes"]) <= 0:
        errs.append("data_episodes 는 양수")
    if int(v["holdout_start_seed"]) <= int(v["data_episodes"]):
        errs.append(f"holdout_start_seed({v['holdout_start_seed']}) 는 data_episodes"
                    f"({v['data_episodes']})보다 충분히 커야 함 — 학습셋 seed 와 겹치면 안 됨(예 90000)")
    ladder = v["ladder"]
    if not ladder or any(int(s) <= 0 for s in ladder):
        errs.append("ladder 는 양의 정수 리스트")
    elif any(ladder[i] >= ladder[i + 1] for i in range(len(ladder) - 1)):
        errs.append(f"ladder={ladder} 는 오름차순(엄격 증가)이어야 함")
    if not (0.0 < float(v["gap_fraction"]) < 1.0):
        errs.append(f"gap_fraction={v['gap_fraction']} 는 (0, 1) 범위여야 함")
    if float(v["fixed_points"]) <= 0:
        errs.append("fixed_points 는 양수(퍼센트 점)")
    if v["task_kind"] == "custom" and not v["description"].strip():
        errs.append("task_kind=custom 이면 description(자연어) 필수")
    if v["task_kind"] == "existing" and not v["env_id"].strip():
        errs.append("task_kind=existing 이면 env_id 필수")
    if not v["name"].strip() or any(c in v["name"] for c in r'\/:*?"<>|'):
        errs.append(f"name={v['name']!r} 이 비었거나 파일명에 못 쓰는 문자 포함")
    if errs:
        raise ValueError("계획 값 오류:\n  - " + "\n  - ".join(errs))


def run_create(out: str | None = None, **overrides) -> Path:
    """기본값 + overrides 로 계획 YAML 을 만들어 저장하고 경로를 반환."""
    v = dict(DEFAULTS)
    v.update({k: val for k, val in overrides.items() if val is not None})
    _validate_create(v)

    rendered = TEMPLATE.format(
        name=v["name"], task_kind=v["task_kind"], env_id=v["env_id"],
        description=v["description"],
        target=v["target"], episodes=v["episodes"], seed=v["seed"],
        holdout_start_seed=v["holdout_start_seed"],
        data_source=v["data_source"], data_episodes=v["data_episodes"],
        hf_dataset_repo=v["hf_dataset_repo"], version=v["version"],
        hf_output_repo=v["hf_output_repo"], finetune_scope=v["finetune_scope"],
        ladder="[" + ", ".join(str(s) for s in v["ladder"]) + "]",
        continue_type=v["continue_type"], gap_fraction=v["gap_fraction"],
        fixed_points=v["fixed_points"],
        confirm_on_ambiguous=str(bool(v["confirm_on_ambiguous"])).lower(),
        approval_mode=v["approval_mode"],
    )
    out_path = Path(out) if out else (PLANS_DIR / f"{v['name']}.yaml")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    return out_path


# ── decide (반복 루프의 숫자 판정 — 결정론) ───────────────────────────────────
def decide_logic(plan: dict, history: list[dict]) -> dict:
    """평가 이력으로 다음 행동을 판정.

    plan     = 로드된 계획 dict
    history  = [{"steps": 3000, "success": 0.62}, ...]  사다리 순서(최신이 마지막)
               success 는 분수(0..1).
    반환 action: train | done | stop | reconfirm
    """
    target = float(plan["goal"]["target_success_rate"])
    loop = plan.get("loop", {})
    ladder = list(loop.get("step_ladder", DEFAULT_STEP_LADDER))
    rule = loop.get("continue_rule", DEFAULT_CONTINUE_RULE)
    confirm = bool(loop.get("confirm_on_ambiguous", True))

    if not history:
        return {"action": "train", "steps": ladder[0],
                "reason": f"첫 학습: 사다리 첫 칸 {ladder[0]}스텝"}

    latest = history[-1]
    cur = float(latest["success"])

    if cur >= target:
        return {"action": "done",
                "reason": f"목표 {target:.2f} 도달 (현재 {cur:.2f})"}

    idx = ladder.index(latest["steps"]) if latest["steps"] in ladder else len(history) - 1
    if idx >= len(ladder) - 1:
        return {"action": "stop", "kind": "exhausted",
                "reason": (f"마지막 칸 {latest['steps']}스텝까지 했지만 {cur:.2f} < 목표 {target:.2f}. "
                           f"스텝 레버 소진 — 남은 카드(데이터↑·full·해상도)는 사람 판단")}

    next_steps = ladder[idx + 1]
    if len(history) == 1:
        return {"action": "train", "steps": next_steps,
                "reason": f"첫 칸 {latest['steps']}스텝={cur:.2f}, 비교 대상 없어 다음 칸 {next_steps} 진행"}

    prev = float(history[-2]["success"])
    improvement = cur - prev
    if rule["type"] == "gap_fraction":
        required = (target - prev) * float(rule["gap_fraction"])
        rule_desc = f"남은거리({target - prev:.2f})×{rule['gap_fraction']}={required:.3f}"
    else:  # fixed_points (퍼센트 점 → 분수)
        required = float(rule["fixed_points"]) / 100.0
        rule_desc = f"고정 +{rule['fixed_points']}점(={required:.3f})"

    band = 0.02  # 기준 ±이 안이면 시험 흔들림과 구분 안 됨 → 재확인
    common = {"improvement": round(improvement, 3), "required": round(required, 3)}
    if confirm and abs(improvement - required) <= band:
        return {"action": "reconfirm",
                "reason": (f"상승 {improvement:+.3f} 이 기준 {rule_desc} 에 아슬하게 걸침(±{band}). "
                           f"같은 칸을 다른 seed 로 재평가해 확인"), **common}
    if improvement >= required:
        return {"action": "train", "steps": next_steps,
                "reason": f"상승 {improvement:+.3f} ≥ 기준 {rule_desc} → 다음 칸 {next_steps} 진행", **common}
    return {"action": "stop", "kind": "plateau",
            "reason": (f"상승 {improvement:+.3f} < 기준 {rule_desc} → 정체. "
                       f"스텝으론 목표 미달 — 사람 판단"), **common}


def run_decide(plan_path: str, history: list[dict]) -> dict:
    import yaml  # 지연 import (create 는 yaml 없이도 동작)
    plan = yaml.safe_load(Path(plan_path).read_text(encoding="utf-8"))
    return decide_logic(plan, history)


# ── CLI ───────────────────────────────────────────────────────────────────────
def _cli_create(a) -> int:
    ladder = [int(s) for s in a.ladder.split(",")] if a.ladder else None
    path = run_create(
        out=a.out, name=a.name, task_kind=a.task_kind, env_id=a.env_id,
        description=a.description, target=a.target,
        data_episodes=a.data_episodes, hf_dataset_repo=a.hf_dataset_repo,
        version=a.dataset_tag, hf_output_repo=a.hf_output_repo, ladder=ladder,
    )
    print(f"[model_plan] 계획 생성 -> {path}")
    return 0


def _cli_decide(a) -> int:
    if a.history_file:
        history = json.loads(Path(a.history_file).read_text(encoding="utf-8"))
    else:
        history = json.loads(a.history or "[]")
    result = run_decide(a.plan, history)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="model_plan", description="모델 개발 계획 생성 + 루프 판정")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="계획 YAML 생성")
    c.add_argument("--name")
    c.add_argument("--out")
    c.add_argument("--task-kind", dest="task_kind", choices=sorted(_ENUMS["task_kind"]))
    c.add_argument("--env-id", dest="env_id")
    c.add_argument("--description")
    c.add_argument("--target", type=float)
    c.add_argument("--data-episodes", dest="data_episodes", type=int)
    c.add_argument("--hf-dataset-repo", dest="hf_dataset_repo")
    c.add_argument("--dataset-tag", dest="dataset_tag", help="데이터셋 스냅샷 태그 (예: v2)")
    c.add_argument("--hf-output-repo", dest="hf_output_repo")
    c.add_argument("--ladder", help="쉼표구분 오름차순 정수, 예: 3000,6000,12000")
    c.set_defaults(func=_cli_create)

    d = sub.add_parser("decide", help="평가 이력으로 다음 행동 판정 (JSON 출력)")
    d.add_argument("--plan", required=True, help="계획 YAML 경로")
    d.add_argument("--history", help='JSON 문자열: [{"steps":3000,"success":0.62}, ...]')
    d.add_argument("--history-file", dest="history_file", help="위 JSON 을 담은 파일")
    d.set_defaults(func=_cli_decide)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # Windows cp949 콘솔에서 —·한글 출력 깨짐/크래시 방지
        except Exception:
            pass

    a = p.parse_args(argv)
    try:
        return a.func(a)
    except (ValueError, KeyError) as e:
        print(f"[model_plan] 오류: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
