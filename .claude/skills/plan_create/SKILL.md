---
name: plan_create
description: 모델 개발 "계획서"(실행 사양 YAML)를 만드는 스킬. 사용자가 만들고 싶은 모델을 자연어로 말하면(예 "빨간 공을 그릇에 넣는 모델, 목표 85%, 손절 빡세게"), 이 스킬이 그걸 `scripts/model_plan.py create` 의 플래그로 옮겨 `plans/<name>.yaml` 을 생성한다. 기본값은 이 하네스가 합의한 값(목표 0.90 / 스텝사다리 3000·6000·12000 / gap_fraction 0.333 / seed 고정 / per_pod 승인) — 사용자가 말한 것만 덮어쓴다. 생성된 YAML 은 이후 `/plan_run` 이 읽어 태스크→데이터→학습→평가→판정 루프를 돌리는 입력. 얇은 래퍼(로직은 model_plan.py). args = 자연어 요청(비면 기본값 그대로).
---

# plan_create — 모델 개발 계획서(YAML) 생성

`scripts/model_plan.py create` 래퍼. 사용자의 자연어 요청을 CLI 플래그로 옮겨 계획 YAML 을 만든다. 로직·검증·기본값은 전부 스크립트에 있고(단일 출처), 이 스킬은 **자연어 → 플래그** 번역만 한다.

흐름: **`/plan_create <자연어>`** → `plans/<name>.yaml` → (사용자 검토) → `/plan_run <그 yaml>`.

## 호출됐을 때

1. `args`(자연어)를 읽어 아래 플래그로 매핑한다. **말하지 않은 건 손대지 않는다** — 스크립트 기본값이 그대로 쓰인다.

   | 사용자가 말한 것 | 플래그 |
   |---|---|
   | 계획 이름 | `--name` (안 주면 태스크에서 유추, 예 `threecubes-90`) |
   | 무슨 태스크 — 기존 env | `--task-kind existing --env-id <Id>-v1` |
   | 무슨 태스크 — 새 태스크(자연어) | `--task-kind custom --description "<자연어>"` |
   | 언어 지시 | `--instruction "pick the red cube"` |
   | 목표 성공률 (예 "85%") | `--target 0.85` |
   | 시험 판 수 | `--episodes 50\|100` |
   | 데이터 출처/규모 | `--data-source task_to_h5\|fetch_sample_h5` · `--data-episodes N` |
   | HF repo | `--hf-dataset-repo …` · `--version vN` · `--hf-output-repo …` |
   | 눈 녹이기 | `--finetune-scope full` (기본 head_only) |
   | 스텝 사다리 | `--ladder 3000,6000,12000` (오름차순) |
   | 손절 성향 | `--continue-type gap_fraction --gap-fraction 0.25(참을성)\|0.333(권장)\|0.5(빡셈)` |
   | 고정점수 방식 원하면 | `--continue-type fixed_points --fixed-points 5\|10` |
   | 승인 방식 | `--approval-mode per_pod\|pre_approved` |

2. 프로젝트 루트에서 실행:
   ```
   <maniskill-python> scripts/model_plan.py create --name <name> [매핑한 플래그…]
   ```
3. 스크립트가 값을 **검증**(enum·target 범위·사다리 오름차순·gap_fraction 범위·custom이면 description 필수 등)한 뒤 `plans/<name>.yaml` 을 쓴다. 실패하면 오류 메시지를 그대로 사용자에게 전달(계획을 잘못 만드는 걸 여기서 막는다).
4. 생성된 경로를 보고하고, **핵심 선택(목표·사다리·손절규칙·승인방식)을 한눈에 요약**한다. 이어서 `/plan_run plans/<name>.yaml` 로 실행함을 안내한다.

## 동작 원리 / 주의사항

- **덮어쓰기 주의**: `--name` 이 기존 계획과 같으면 그 YAML 을 덮는다. 같은 이름이면 사용자에게 먼저 확인.
- **파일 생성은 무과금·가역** — 자율 진행 가능. 실제 과금(파드)은 `/plan_run` 단계에서만 발생.
- 값 매핑이 애매하면(예 "적당히 빡세게") 추측하지 말고 사용자에게 한 번 되묻는다 — 계획서는 이후 자동 루프의 계약이라 초기값이 중요.
- 이 스킬은 계획을 **만들기만** 한다. 실행(태스크 생성·데이터·학습·평가)은 `/plan_run` 이 한다.
- **custom 태스크는 `/add_custom_task` 가능 범위만** — ManiSkill 한계상 강체·panda 테이블탑·모션플래닝으로 풀리는 것만이다(천/유체/손재주는 불가). plan_create 는 YAML 만 만들고, 실제 가능 판정은 `/plan_run` 이 `/add_custom_task` 로 검증한다(불가능하면 거기서 거절·중단).

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/plan_create` | 기본값 그대로 `plans/my-model-plan.yaml` |
| `/plan_create ThreeColoredCubes 목표 90%` | `--env-id ThreeColoredCubes-v1 --target 0.90` |
| `/plan_create 빨간 공을 그릇에 넣기, 목표 80%, 손절 빡세게` | `--task-kind custom --description "빨간 공을 그릇에 넣기" --target 0.80 --gap-fraction 0.5` |
| `/plan_create 스텝 5000,10000,20000 로, 눈 녹여서` | `--ladder 5000,10000,20000 --finetune-scope full` |
