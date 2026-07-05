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
    "instruction": "pick the red cube",
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
    "max_usd": 30,
    "max_train_runs": 3,
}

_ENUMS = {
    "task_kind": {"existing", "custom"},
    "data_source": {"task_to_h5", "fetch_sample_h5"},
    "finetune_scope": {"head_only", "full"},
    "continue_type": {"gap_fraction", "fixed_points"},
    "approval_mode": {"per_pod", "pre_approved"},
}

# ── YAML 템플릿 (단일 출처 — plans/model_plan.template.yaml 은 이걸로 생성됨) ──────
TEMPLATE = """\
# 모델 개발 계획 — 실행 사양 (YAML)   [model_plan.py create 로 생성됨]
# ─────────────────────────────────────────────────────────────
# /plan_run 이 이 사양대로 [태스크→데이터→학습→평가→판정] 루프를
# 목표 성공률 도달 또는 정지조건까지 반복한다.
# 각 항목 주석의 "선택지"에서 값을 바꿔 다양한 전략을 고를 수 있다.

# ── 1. 미션: 무슨 모델을 만드나 ──────────────────────────────
mission:
  name: {name}
  task:
    kind: {task_kind}                  # 선택지: existing | custom
    env_id: {env_id}                   # kind=existing 일 때. 지원목록은 /task_to_h5 참고
    description: "{description}"        # kind=custom 일 때 자연어 → /plan_run 이 먼저 /add_custom_task
  instruction: "{instruction}"         # 평가·학습에 쓰는 언어 지시

# ── 2. 목표: 성공 기준 ───────────────────────────────────────
goal:
  target_success_rate: {target}        # 이 점수 도달 = 임무 완료
  eval:                                # 평가 조건 (반복 내내 고정 → 비교 가능)
    episodes: {episodes}               # 홀드아웃 평가셋 크기(=eval count). 선택지: 50 | 100
    seed: {seed}                       # 평가 샘플 RNG 고정 → 매 반복 동일 비교
    holdout_start_seed: {holdout_start_seed}          # 학습셋(0..N)과 겹치지 않는 씬 seed 시작점 (train/test 분리, eval_method=v2)
    action_steps: 16                   # 하네스 기본값(호라이즌 최대=최적). 바꾸지 않음
    budget_factor: 3                   # 하네스 기본값(궤적길이×3). 바꾸지 않음

# ── 3. 데이터 & 초기 학습 ────────────────────────────────────
data:
  source: {data_source}                # 선택지: task_to_h5(직접 생성) | fetch_sample_h5(공식 데모)
  episodes: {data_episodes}            # 초기 데이터 규모
  hf_dataset_repo: {hf_dataset_repo}
  version: {version}                   # 불변 버전 태그
training:
  hf_output_repo: {hf_output_repo}
  finetune_scope: {finetune_scope}     # 선택지: head_only(기본) | full(tune_visual·눈녹이기·과금 큼)

# ── 4. 반복 루프: 스텝 사다리 + 정지 정책 (핵심) ─────────────
loop:
  lever: steps                         # 자동 루프가 돌리는 손잡이. 지금은 steps 하나
  step_ladder: {ladder}                # 낮은 칸부터 오름 (오름차순 정수)
  continue_rule:                       # "이번 칸에서 충분히 올랐나?" → 다음 칸 진행 판정
    type: {continue_type}              # 선택지: gap_fraction | fixed_points
    gap_fraction: {gap_fraction}       # 남은거리(target−현재)의 이 비율 이상 올라야 계속
                                       #   선택지: 0.25(참을성) | 0.333(권장·60점→+10) | 0.5(빡센 손절)
    fixed_points: {fixed_points}       # (type=fixed_points 일 때) 앞 칸보다 +이 절대점수 이상 (선택지: 5 | 10)
  confirm_on_ambiguous: {confirm_on_ambiguous}   # 기준에 아슬하면 다른 seed 로 한 번 더 확인
  stop:                                # 아래 중 하나라도 걸리면 루프 종료 + 알람
    on_target_reached: true            # 목표 도달 → "성공"
    on_plateau: true                   # continue_rule 미달 → "스텝으론 안 됨"
    on_ladder_exhausted: true          # 마지막 칸까지 미달 → "스텝 다 써봤는데 안 됨"
  # 스텝 사다리 소진 후에도 목표 미달이면 남은 카드(데이터↑·full·해상도)는
  # 비용·판단이 커서 자동 안 함 → 알람으로 사람에게 넘긴다.

# ── 5. 예산 & 승인 (과금 게이트) ─────────────────────────────
budget:
  approval_mode: {approval_mode}       # 선택지: per_pod(매 파드 승인) | pre_approved(한도 내 자율)
  max_usd: {max_usd}                   # pre_approved 상한 (또는 전체 상한)
  max_train_runs: {max_train_runs}     # 최대 학습 횟수 (사다리 칸 수와 맞물림)
  max_concurrent_pods: 1
  auto_runpod_down: true               # 평가·서빙 끝나면 파드 자동 종료(과금 중단·자율)

# ── 6. 알림 ──────────────────────────────────────────────────
notify:
  channel: discord                     # 진행·종료 알람 채널
  on: [success, plateau, exhausted, error, awaiting_approval]
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
        description=v["description"], instruction=v["instruction"],
        target=v["target"], episodes=v["episodes"], seed=v["seed"],
        holdout_start_seed=v["holdout_start_seed"],
        data_source=v["data_source"], data_episodes=v["data_episodes"],
        hf_dataset_repo=v["hf_dataset_repo"], version=v["version"],
        hf_output_repo=v["hf_output_repo"], finetune_scope=v["finetune_scope"],
        ladder="[" + ", ".join(str(s) for s in v["ladder"]) + "]",
        continue_type=v["continue_type"], gap_fraction=v["gap_fraction"],
        fixed_points=v["fixed_points"],
        confirm_on_ambiguous=str(bool(v["confirm_on_ambiguous"])).lower(),
        approval_mode=v["approval_mode"], max_usd=v["max_usd"],
        max_train_runs=v["max_train_runs"],
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
    ladder = list(plan["loop"]["step_ladder"])
    rule = plan["loop"]["continue_rule"]
    confirm = bool(plan["loop"].get("confirm_on_ambiguous", True))

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
        description=a.description, instruction=a.instruction, target=a.target,
        episodes=a.episodes, seed=a.seed, holdout_start_seed=a.holdout_start_seed,
        data_source=a.data_source,
        data_episodes=a.data_episodes, hf_dataset_repo=a.hf_dataset_repo,
        version=a.version, hf_output_repo=a.hf_output_repo,
        finetune_scope=a.finetune_scope, ladder=ladder,
        continue_type=a.continue_type, gap_fraction=a.gap_fraction,
        fixed_points=a.fixed_points, approval_mode=a.approval_mode,
        max_usd=a.max_usd, max_train_runs=a.max_train_runs,
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
    c.add_argument("--instruction")
    c.add_argument("--target", type=float)
    c.add_argument("--episodes", type=int)
    c.add_argument("--seed", type=int)
    c.add_argument("--holdout-start-seed", dest="holdout_start_seed", type=int,
                   help="홀드아웃 평가셋 씬 seed 시작점 (학습셋과 겹치지 않게, 기본 90000)")
    c.add_argument("--data-source", dest="data_source", choices=sorted(_ENUMS["data_source"]))
    c.add_argument("--data-episodes", dest="data_episodes", type=int)
    c.add_argument("--hf-dataset-repo", dest="hf_dataset_repo")
    c.add_argument("--version")
    c.add_argument("--hf-output-repo", dest="hf_output_repo")
    c.add_argument("--finetune-scope", dest="finetune_scope", choices=sorted(_ENUMS["finetune_scope"]))
    c.add_argument("--ladder", help="쉼표구분 오름차순 정수, 예: 3000,6000,12000")
    c.add_argument("--continue-type", dest="continue_type", choices=sorted(_ENUMS["continue_type"]))
    c.add_argument("--gap-fraction", dest="gap_fraction", type=float)
    c.add_argument("--fixed-points", dest="fixed_points", type=float)
    c.add_argument("--approval-mode", dest="approval_mode", choices=sorted(_ENUMS["approval_mode"]))
    c.add_argument("--max-usd", dest="max_usd", type=float)
    c.add_argument("--max-train-runs", dest="max_train_runs", type=int)
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
