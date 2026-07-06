---
name: plan_run
description: 모델 개발 "계획서"(plan_create 가 만든 실행 사양 YAML)를 읽어, 목표 성공률에 도달할 때까지 실제 파이프라인을 반복 실행하는 오케스트레이션 스킬. add_custom_task 처럼 결정론적 스크립트가 아니라 AI(나)가 절차를 따라 다른 스킬들을 호출한다 — 신뢰성은 내 판단이 아니라 (1) 반복 판정을 결정론으로 내는 `scripts/model_plan.py decide` 와 (2) 각 하위 스킬의 게이트(add_custom_task 검증·ee_verify·gr00t_eval)에서 나온다. 흐름: 스테이지0 태스크(custom이면 /add_custom_task) → 스테이지1 데이터(task_to_h5→h5_add_images→ee_verify→h5_to_lerobot→hf_push_dataset) → 루프(승인→gr00t_train→gr00t_serve→gr00t_eval→runpod_down→decide) → 목표달성/정체/소진 시 종료+알람. 과금(파드 생성)만 승인받고 무과금·판정·파드종료는 자율(CLAUDE.md 규칙2). args = 계획 YAML 경로(예 `plans/threecubes-90.yaml`).
---

# plan_run — 계획서대로 목표까지 반복 실행

계획 YAML 을 계약으로 삼아 **태스크 생성 → 데이터 → 학습 → 평가 → 판정** 루프를 목표 도달/정지조건까지 돌린다. 이 스킬은 스크립트가 아니라 **AI(나)가 절차를 따라 하위 스킬을 호출**하는 메타 스킬이다. 내 산수·감을 믿지 않는다 — **매 반복의 "다음에 뭘" 판정은 `model_plan.py decide` 에 위임**하고 그 결과에 복종한다.

> 신뢰의 근원: ① 반복 판정 = `decide`(결정론, gap_fraction 산수). ② 각 단계의 옳음 = 하위 스킬 게이트(add_custom_task 검증 / ee_verify / gr00t_eval 성공률). 내가 "됐다"고 선언하지 않는다.

## 0. 계획 읽기

`args` 의 YAML 경로를 읽는다(없으면 `plans/` 목록을 보여주고 요청). `mission·goal·data·training·loop·budget·notify` 를 파악. 이후 모든 값은 이 파일에서만 온다(태스크 이름조차 하드코딩 금지 — 계약만 읽는다).

## 스테이지 0 — 태스크 준비

- `mission.task.kind == existing`: `env_id` 를 그대로 쓴다. `/task_to_h5` 지원목록에 있는지만 확인.
- `mission.task.kind == custom`: 그 env 가 이미 구현돼 있는지 본다(`scripts/custom_envs.py` 등록 여부). **미구현이면 `/add_custom_task "<description>"` 를 먼저 호출** → 구현+검증. **검증 PASS 라야 진행**. add_custom_task 가 거절(불가능한 태스크)하거나 검증 FAIL 이면 **여기서 멈추고 알람**(그 이유 그대로).
  - 이 단계는 sim·코드편집(무과금·가역)이라 자율 진행.

## 스테이지 1 — 데이터 준비 (멱등)

**학습셋**과 **홀드아웃 평가셋**을 따로 만든다 (평가는 학습에 없던 씬에서). 전부 로컬/WSL·무과금.

**학습셋** — `data.hf_dataset_repo @ version` 이 이미 HF 에 있으면 **건너뛴다**(`/hf_push_dataset --verify-only`). 없으면:
1. `/task_to_h5 <env_id> <data.episodes>` (또는 `data.source==fetch_sample_h5` 면 `/fetch_sample_h5 <env_id>`)
2. `/h5_add_images <env_id> <data.episodes>` → 학습용 이미지 h5
3. `/ee_verify <그 h5>` — **게이트**. 재현율/ik_fails 가 나쁘면 멈추고 알람(데이터·변환 문제지 학습으로 덮을 게 아님).
4. `/h5_to_lerobot <그 h5>` → LeRobot 디렉토리
5. `/hf_push_dataset <lerobot 디렉토리> <hf_dataset_repo> --version <version>` → 파드가 받아감

**홀드아웃 평가셋** — 학습셋과 **겹치지 않는 seed** 로 (커스텀 태스크만; lerobot/hf 변환 불필요). 이미 있으면 재사용:
6. `/task_to_h5 <env_id> <goal.eval.episodes> --start-seed <goal.eval.holdout_start_seed> --traj-name holdout`
7. `/h5_add_images <env_id> <goal.eval.episodes>` (입력 = 그 holdout 궤적) → **홀드아웃 이미지 h5** = 스테이지2 평가 입력(경로 기억)

산출: 학습용 HF repo(파드행) + **홀드아웃 평가 h5**(스테이지2에서 반복 사용, `eval_method=v2`). 학습셋 h5 를 평가에 쓰지 않는다.

## 스테이지 2 — 반복 루프 (핵심)

`history = []` 로 시작. `decide` 가 멈추라 할 때까지:

1. **다음 행동 판정** — 매번 아래를 호출하고 그 `action` 에 복종:
   ```
   <maniskill-python> scripts/model_plan.py decide --plan <yaml> --history '<history JSON>'
   ```
   - `train(steps)` → 2번으로. `done` → 성공 종료. `stop(plateau|exhausted)` → 종료. `reconfirm` → 6번.
2. **과금 게이트** (train·serve 는 GPU 파드 = 과금):
   - `budget.approval_mode == per_pod`: "반복 N: {steps}스텝 학습 + 서빙 파드를 띄웁니다(대략 $X)" 한 줄 **승인 요청**(`awaiting_approval` 알람). 승인 전엔 파드 안 만듦.
   - `pre_approved`: 파드 생성 **자율** — 봉투는 계획서의 **유한한 `step_ladder`**(사다리를 다 돌면 끝). CLAUDE.md 규칙2 예외("유한한 step_ladder = 사전 선언된 봉투, plan_run 컨텍스트 한정")에 근거.
3. **학습** — `/gr00t_train --max-steps <steps> --hf-dataset-repo <data repo> --hf-output-repo <training.hf_output_repo>` (+ `training.finetune_scope==full` 이면 `--full`). 학습 파드는 업로드 후 **자가종료**.
4. **서빙** — `/gr00t_serve <업로드된 hf_model>`. 파드 IP/포트는 내가 직접 얻는다(`runpod_client.pod().portMappings` — CLAUDE.md 규칙3, 사용자에게 안 물음).
5. **평가** — `/gr00t_eval <스테이지1 홀드아웃 h5> --server-host <ip> --count <goal.eval.episodes> --seed <goal.eval.seed> --instruction "<mission.instruction>"`. 성공률을 읽는다 (학습 안 쓴 씬 = eval v2).
6. **파드 종료** — `auto_runpod_down` 이면 서빙 파드 `/runpod_down <id> --yes`(과금 중단·자율). `reconfirm` 이면 종료 **전에** 같은 체크포인트를 다른 seed 로 한 번 더 평가해 확인.
7. **기록 & 안내** — `history` 에 `{steps, success}` 추가. MANIFEST 에 eval 기록(홀드아웃이므로 v2): `<maniskill-python> scripts/manifest.py set-eval <task> <model> <success> --method v2`. 사용자에게 진행 메시지(`notify.channel`): 예 *"6000스텝=0.80, 남은거리 1/3(0.093) 넘음 → 12000 진행"*. 1번으로 돌아감.

## 종료 (알람)

- `done` → **성공 알람**: 최종 성공률·모델 HF 좌표(MANIFEST). 
- `stop plateau/exhausted` → **알람**: 어디서 멈췄나 + `decide` 의 이유. 스텝 레버로는 목표 미달이므로 **남은 카드(데이터↑·`--full`·해상도/각도)를 사람 판단으로 넘김**(자동으로 그 비싼 레버를 당기지 않는다).
- 어느 종료든 `/runpod_ls` 로 떠 있는 파드 없는지 확인하고 정리.

## 과금·안전 규칙 (CLAUDE.md)

- **승인 필요(사람)**: GPU 파드 생성(train·serve). `per_pod` 는 매번, `pre_approved` 는 계획서의 `step_ladder` 를 도는 동안 자율.
- **자율(무과금·과금중단·가역)**: 태스크 생성·데이터 전체·평가 롤아웃(로컬 WSL)·`decide`·파드 **종료**(runpod_down).
- **못 하는 것만 사람에게**: 승인·시크릿·콘솔로그. 파드 IP/포트 등 프로그램으로 얻히는 건 직접.
- 한 단계가 **2번 실패하면 멈추고 보고**(우회 연쇄 금지). 게이트 FAIL(ee_verify·검증)은 학습으로 덮지 말고 그대로 알람.

## 호출됐을 때 (절차 요약)

1. YAML 로드(없으면 요청).
2. 스테이지 0 태스크 → 스테이지 1 데이터(멱등).
3. 스테이지 2 루프: `decide` 복종 → 승인 → train → serve → eval → down → 기록·안내.
4. 종료 시 최종 알람 + 파드 정리.

## 주의사항

- **판정을 눈대중하지 않는다** — "올랐으니 계속" 같은 감 금지. 매 반복 `decide` JSON 을 그대로 따른다.
- **평가 조건 고정** — `episodes·seed·action_steps·budget_factor` 는 반복 내내 계획값 그대로(안 바꿔야 반복 간 숫자가 비교됨).
- **파드 위생** — 매 반복 끝과 실패 시 파드가 남지 않게 확인. 잊고 켜두면 과금 샌다.
- **멱등** — 데이터·태스크는 이미 있으면 재사용. 중간에 끊겨 재실행해도 처음부터 다시 굽지 않는다.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/plan_run plans/threecubes-90.yaml` | 그 계획대로 데이터→학습 루프를 0.90 도달/정체까지 반복 |
| `/plan_run plans/redball-bowl-80.yaml` | custom 태스크라 먼저 /add_custom_task 로 구현·검증 후 루프 |

흐름: `/plan_create <자연어>` → (YAML 검토) → **`/plan_run <yaml>`** → (승인 게이트들) → 목표 도달 또는 사람 호출.
