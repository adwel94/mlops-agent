---
name: add_custom_task
description: 사용자가 자연어로 설명한 새 커스텀 task 를 (1) 구현 가능한지 판단하고(말도 안 되는 건 거절) (2) 가능하면 하네스 계약을 지켜 구현하고(custom_envs 환경 클래스 + custom_solutions 솔루션 + CUSTOM_TASKS 등록) (3) scripts/validate_custom_task.py 로 계약·EE 재현을 검증하는 메타 스킬. 기존 스킬들과 달리 "되냐 판단 + 구현"은 결정론적 스크립트가 아니라 이 절차를 따르는 AI 가 수행하고, 신뢰성은 검증 스크립트(정적 계약 + 동적 EE/IK 재현)에서 나온다. EE 방식을 지향하므로 tcp_pose·base_camera 계약이 핵심. args = task 자연어 설명(예: "빨간 공을 그릇에 넣기"). 동적 검증은 WSL(mplib) 필요.
---

# add_custom_task — 새 커스텀 task 판단·구현·검증

사용자가 자연어로 새 task 를 설명하면: **① 가능 여부 판단 → ② 구현 → ③ 코드 검증**. 이 스킬은 결정론적 스크립트가 아니라 **AI(나)가 이 절차를 따라 수행**하는 메타 스킬이다 (env/솔루션 생성은 추론·코딩 작업이라 함수로 못 짠다). 신뢰성은 내 판단이 아니라 마지막 **검증 스크립트**에서 나온다.

> 배경: 하네스의 소비 스킬(②③④⑤)은 task 이름을 모르고 **약속(계약)만** 따른다. 그래서 새 task 가 그 약속을 지키면 소비 스킬을 안 고치고 재사용된다. 이 스킬의 목적 = "약속을 지키는 task 를 만들고, 지켰는지 코드로 증명".

## ① 가능 여부 판단 (고맥락 — 내가 판단, 코드 아님)

이 하네스에서 "가능"의 진짜 게이트는 *시뮬되느냐*가 아니라 **모션플래닝 솔루션을 스크립트로 짤 수 있느냐 + 성공을 코드로 잴 수 있느냐**다. 아래 루브릭으로 판단한다:

**가능 (구현 진행):**
- 임베디먼트: **panda 단일 팔, 테이블탑**.
- 객체: **강체**(rigid body) — 큐브/공/페그/도구 등.
- 동작: 모션플래닝 프리미티브 조합으로 표현 가능 — reach / grasp / lift / place / push / pull / insert. (예: "큐브 3개 쌓기", "빨간 공을 그릇에 넣기", "막대를 구멍에 꽂기")
- 성공: 객체·로봇 상태(pose/grasp/거리/높이)로 **프로그램 판정 가능**.

**거절 (이유 명시):**
- 변형체/천/유체/밧줄("셔츠 접기", "물 따르기", "끈 묶기") — 강체 아님.
- 손재주·접촉 풍부("병뚜껑 돌려 열기", "가위질") — 모션플래닝 프리미티브로 안 됨.
- 다중 팔 / 이동 로봇 / panda 아닌 임베디먼트 — 임베디먼트 가정 위반.
- 성공을 코드로 못 재는 모호한 목표("예쁘게 정리해줘").

**애매하면 거절 말고 사용자에게 한 번 되묻는다** (목표·성공 기준 명확화). 확신 안 서면 "거절"이 아니라 "질문". 그래도 안 되면 가장 가까운 가능한 변형을 제안.

판단을 사실로 포장하지 말 것 — 최종 진실은 ③ 검증(솔루션이 실제로 푸는가)이 본다. 내가 "가능"이라 봤어도 검증이 FAIL 이면 그게 답이다.

## ② 구현 (계약을 지켜서)

문서 "커스텀 task 추가하기" 레시피 그대로, **세 파일**만 손댄다 (소비 스킬은 안 건드림):

1. **`scripts/custom_envs.py`** — `@register_env("<Id>-v1", ...)` 환경 클래스. 표준 ManiSkill env 메서드(`_load_scene`=씬 구성 / `_initialize_episode`=시드 랜덤화 / `evaluate`=성공 판정)를 구현하고, 아래 계약을 반드시 충족:
   - **주 카메라 = `base_camera`** — panda 테이블탑 베이스(예: `PickCubeEnv`)를 상속하면 자동으로 그렇게 된다. 직접 센서를 정의하면 첫 카메라 이름을 `base_camera` 로. *(이게 어긋나면 학습/서빙 modality 불일치)*
   - **`_get_obs_extra` 에 `tcp_pose` 필수** — `tcp_pose=self.agent.tcp_pose.raw_pose`. ④ EE 분기 전체의 생명줄. 그 외 태스크 신호(목표 위치/라벨)도 여기에.
   - **`evaluate()` 가 `{"success": ...}` 반환** — 성공의 정의는 여기서 내가 정한다(예: 타겟을 잡고 들어올림). 이게 검증·라벨·평가의 ground truth.
   - *(언어 지시형이면)* **`label_metadata()`** — 정수 라벨 → 문자열 사전. 데이터셋만으로 지시문 해독 가능하게.
   - *(언어 지시형이면)* **`instruction_template()`** — 언어 명령 틀(예: `"put the {target_id} cube in the bowl"`). `{키}` 는 `label_metadata` 키로 채워진다. 학습(h5_to_lerobot)·평가(gr00t_eval)가 **이 하나만 읽어** 문구가 어긋나지 않는 단일 출처. (검증이 존재·채움가능을 확인)
2. **`scripts/custom_solutions.py`** — 모션플래닝 솔루션 함수 + `SOLUTIONS["<Id>-v1"] = solve_fn` 등록. 기존 솔루션(예: `solve_three_colored_cubes`)을 본보기로.
3. **`scripts/task_to_h5.py`** 의 `CUSTOM_TASKS` 에 task id 추가.

## ③ 검증 (코드 — 신뢰의 근원)

```
<maniskill-python> scripts/validate_custom_task.py <Id>-v1 [--count 3]
```

- **[static]** (Windows, 빠름): CUSTOM_TASKS·SOLUTIONS 등록 / 주 카메라=`base_camera` / `tcp_pose` 존재 / `evaluate().success` 존재. 먼저 `--static-only` 로 빠르게 계약부터 확인 가능.
- **[dynamic]** (WSL, mplib): `task_to_h5 → h5_add_images → ee_verify` 실제 파이프라인을 작은 규모로 흘려, **솔루션이 실제로 풀고**(orig success>0) **EE 모션이 역기구학으로 재현되는지**(reproduction_rate, ik_fails) 확인.

검증이 FAIL 이면:
- static FAIL(카메라/tcp_pose/success) → ②의 env 를 고치고 재검증.
- dynamic FAIL(솔루션이 못 풂 / IK 재현 안 됨) → 솔루션을 디버그하고 재검증.
- **시도 예산: 같은 접근 2회 실패하면 멈추고 보고** (CLAUDE.md 협업 규칙). 우회로 연쇄 금지.

## 호출됐을 때 (절차 요약)

1. `args`(자연어 task 설명) 파싱. 비면 사용자에게 설명을 요청.
2. **판단** — 루브릭으로 가능/거절/되묻기. 거절이면 이유와 함께 멈춤(구현 안 함).
3. **구현** — 세 파일 편집 (계약 충족). 커밋 전 사람이 볼 수 있게 변경 제시.
4. **검증** — `validate_custom_task.py` 실행. static 먼저, 통과하면 dynamic.
5. **보고** — PASS면 성공률/재현율과 함께 "사용 가능", FAIL이면 결함을 헤드라인으로.

## 동작 / 주의사항

- 이 스킬은 다른 모든 스킬이 소비하는 per-task 파일을 *생성*하는 **메타 스킬** — 잘못 생성하면 `custom_envs.py` 를 오염시키니 신중히, 검증 통과 전엔 "완료"라 하지 않는다.
- 동적 검증은 sim 실행(무과금·가역) — 진행 가능. 단 WSL 전제(SETUP.md).
- "산출물 무결성": 검증 PASS = 약속한 것을 온전히 냈다. 검증 없이 "구현 완료"라 보고하지 않는다.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/add_custom_task 빨간 공을 그릇에 넣기` | 가능 판단 → env+솔루션 구현 → 검증 → PASS/FAIL 보고 |
| `/add_custom_task 셔츠를 개기` | 거절 (변형체 — 모션플래닝 솔루션 불가), 이유 설명 |

흐름: **`/add_custom_task <설명>`** → (검증 PASS) → `task_to_h5` → `h5_add_images` → … (기존 파이프라인).
