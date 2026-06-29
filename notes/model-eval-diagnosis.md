# 모델 저성능 진단 — 왜 v1-s20000이 18%에 머무는가

> 이 문서는 **요약·원장**(제약·후보표·결과표·가설 히스토리). 전 과정을 흐름대로 풀어쓴
> **상세 내러티브**(문제→가설→검증을 어떻게 했나→결과, 메커니즘 포함)는
> `eval-investigation-log.md` 참조.

## 0. 한 줄 결론 (검증 완료 후 최종)

병목은 **모델의 reaching 정밀도** — 목표 *색*은 94%로 정확히 식별하지만(언어 OK), 손을
큐브에 정밀히 못 가져가 평균 8cm 빗나간다. 측정 정직성(평가 디코드 경로 재현율 100%)·
데이터 품질(100%)·실행 주기(16 최적)·언어(94%)를 다 검증해 배제 → 남는 건 **단일 고정
카메라에서의 reaching 정밀도 한계**. 처방 후보 두 갈래: **B(warm-start full-tune, visual 해동)**
= 같은 카메라로 "눈"만 녹여 짜냄(싸고 빠름, 단 단일 캠 깊이 모호성은 잔존), **D(손목 카메라
추가)** = 데이터 재생성+재학습으로 근본 처방(§7 — NVIDIA/Seeed 공식 권장 세팅이 손목+정면
2캠). C(에피소드 증량)는 양 plateau+품질 perfect라 후순위. (초기 가설 "head-only라 색 선택
실패"는 correct_color 94%로 **반증됨.**)

## 1. 진짜 원인이 만족해야 하는 제약 (eval 결과)

`orig_success=50/50 · policy_success=9/50(18%) · ik_fails=0`

- **loss 1.06→0.03 수렴** → 모델은 학습 타깃을 거의 완벽히 재현(학습 자체는 정상).
- **ik_fails=0** → 모델이 내는 EEF pose는 전부 IK로 풀리는 "그럴듯·도달가능"한 pose
  (출력이 쓰레기가 아님 → gross한 회전 표현 오염은 가능성 낮음).
- **3k=20k=18%** → 스텝/수렴은 병목이 아님(더 학습해도 안 늘어남).

→ 종합: "모델이 plausible·reachable하게 움직이는데 과제만 못 푼다." 학습량 문제 아님.

## 2. 의심 후보 — 증거로 무엇이 남고 무엇이 빠지나

| 후보 | 판정 | 근거 |
|---|---|---|
| **A. head-only가 언어 grounding 못 함**(LLM·visual freeze) | **유력(남음)** | 집기 ~55% × 색 랜덤 1/3 ≈ 18%로 정확히 일치. frozen이라 스텝 늘어도 grounding 안 늚 → 3k=20k 설명됨 |
| B. 정규화/relative_stats 누락 | **배제** | 학습이 정상 완료(loss 수렴)+serve가 같은 체크포인트 로드 = 학습·추론 정규화 자기일관. `repair_lerobot_metadata.py` 부재는 문서 정리 문제지 입증된 결함 아님 |
| C. Path A(절대 rot6d) 미검증 "갭" | **배제(중복)** | 저장 액션=`pose[t+1]`, `ee_verify` 타깃=재구성된 `pose[t+1]`(recon err~0), rot6d round-trip~3e-7. 둘이 같은 pose를 같은 IK에 넣음 → ee_verify ~100%면 Path A도 ~100%. 별도 오프라인 게이트는 중복 |
| D. train/eval 이미지 도메인 갭(Win CPU render vs WSL llvmpipe) | 약(보류) | frozen visual이라 못 메움. 단 A가 더 단순하게 설명 |
| E. rot6d↔GR00T 내부 SE(3) 규약 | 약 | ik_fails=0이 gross corruption을 약하게 반증 |
| F. replan 거칢(action_steps=16) | 약 | 절대 타깃이라 드리프트 누적 없음 |

핵심: **B·C가 빠지면서(데이터·정규화 결백) 화살이 A로 집중**된다.

## 3. 분기 진단 — A냐 아니냐를 싸게 가른다

평가에서 **target 성공만이 아니라 "아무 큐브나 grasp+lift 했나"**를 같이 센다
(`ThreeColoredCubesEnv`가 WSL eval 안에서 `base.cubes` 3개를 노출 → env 내부로 per-cube
grasp/lift 직접 읽음. 색 순서는 sidecar `label_metadata.target_id`에서 매핑).

판정:
- **any-pick ~55% 인데 correct-color만 18%** → A 확정 → **full-tune(실험 B)로.**
- **any-pick도 18%** → 조작/표현 자체가 병목 → D/E/F 재조사(full-tune 헛수고).

부수 계측(같은 롤아웃에서 공짜로): 에피소드별 ik_fails, 큐브별 max lift,
최종 tcp→target 거리, 사용 스텝, 뽑은 색. → `*.eval_diag.jsonl` 로 떨군다.

## 4. 과금 구조 (정정: 무과금 아님)

| 부분 | 위치 | 과금 |
|---|---|---|
| 정책 서버(모델 추론) | RunPod L40S | **O** |
| 롤아웃(sim·IK·계측) | 로컬 WSL | X |

진단 1은 **이전 18% 측정과 동일한 serve+eval 1회**(새 학습 없음, 평가 코드만 보강).
full-tune보다 훨씬 싸지만 **공짜는 아니다** — serve 파드 가동시간만큼 과금.
→ 코드 보강은 지금(무과금), serve 파드는 별도 승인 후.

## 5. 측정 결과 (2026-06-29, v1-s20000, L40S serve, 50ep seed=0)

```
policy_success=16/50(32%)  any_pick=17/50(34%)  correct_color_rate=0.941  ik_fails=0
no-pick 실패 시 최종 tcp→target 거리 평균 8.4cm (성공 시 1.1cm)
```

**가설 A 반증.** 색 선택은 94%로 거의 완벽 → 언어 grounding은 병목이 아니다.
진짜 병목은 **reaching/grasping 정밀도**: 66% 에피소드에서 손이 큐브에 못 닿고
(평균 8cm 떨어진 채 종료) 한 번도 못 든다. 닿기만 하면(1.1cm) 성공하고 색도 맞춘다.

함의 — 처방이 바뀐다:
- **full-tune(B)는 우선순위 하락**: 언어가 이미 풀려 LLM 해동 효과 작음. visual 해동이
  reaching에 약간 도움 될 수 있으나 핵심 레버 아님.
- **action_steps 축소 재평가(가장 쌈)**: 현재 16스텝 open-loop. reaching이 살짝 어긋날 때
  중간 교정을 못 함 → `--action-steps 4~8`로 더 자주 replan하면 closed-loop 교정으로
  reach율이 오를 수 있다. 모델 재학습 없이 serve+eval만(같은 파드 재사용).
- **데이터 증강(C)이 B보다 on-target**: 액션 헤드의 reaching 정밀도는 demo 수에 직결.

주의 — **확산 정책 분산**: 동일 모델·seed인데 이전 18% → 이번 32%. GR00T 액션 헤드가
diffusion이라 샘플마다 다름 → 50ep 단발은 CI 넓다(참값 ~25%±). any-pick/색 분해 신호는
견고하지만, 성공률 절대값 비교엔 더 많은 ep 또는 고정 샘플링이 필요.

상세: `data/datasets/ThreeColoredCubes-v1/motionplanning.rgb.pd_joint_pos.physx_cpu.eval_diag.as16.jsonl`

## 6. 가설 히스토리 (시간순 — 무엇을 의심→어떻게 검증→결과)

문제: v1-s20000 성공률이 낮다(처음 18%로 측정). "왜?"의 가설이 어떻게 바뀌어 왔는가.

| # | 가설 | 검증 방법 | 결과 |
|---|---|---|---|
| **H1** | 데이터/정규화 결함 (Path A 미검증 갭 · relative_stats 누락) | 이미 가진 증거로 반증 시도 | **배제**. ee_verify(~100%)+rot6d round-trip(3e-7)로 Path A 사실상 검증됨(중복). 학습 정상완료+serve 동일 체크포인트 = 정규화 자기일관. (사용자 반박으로 정정 — 부록 참조) |
| **H2** | head-only라 **언어 grounding(색 선택)** 을 못 배움. 집기 ~55%×색 랜덤 1/3 ≈ 18% | eval에 any-pick/correct-color 계측 추가 → serve+50ep | **반증**. correct_color_rate=**94%** → 색은 거의 완벽히 고름. 언어는 병목 아님 |
| **H3** | 병목은 **reaching**: 16스텝 **open-loop 드리프트** (피드백 없이 누적 오차 → 8cm 빗나감) | action_steps 16→8→4 재평가 (재학습 X, serve+eval) | **검증 중** (이 실행) |
| **H3b** | (H3 대안) 드리프트가 아니라 **처음부터 조준이 틀림** — 정밀도/데이터 부족 | H3 테스트가 자동으로 가름 | action_steps 줄여도 reach율 안 오르면 → 이쪽 → 데이터 증강(C) |

관측 근거(H2→H3 전환의 핵심, 50ep):
- correct_color_rate 94%(16/17): 집은 큐브는 거의 항상 목표색 → "뭘 집을지"는 앎.
- any_pick 34%(17/50): 아무 큐브나 드는 것 자체가 1/3 → 조작이 병목.
- 실패 시 최종 tcp→target 8.4cm vs 성공 시 1.1cm: 큐브 근처도 못 감.
- ik_fails 0: 요청 자세는 다 도달가능 → 실행부 아닌 **정책의 목표 선정**이 문제.

검증 설계(H3): 학습 호라이즌 16은 불변, **실행** action_steps만 낮춰 닫힌 루프 교정을
자주 줌. open-loop 드리프트가 범인이면 reach율↑(H3 지지), 안 오르면 조준 문제(H3b).
diffusion 정책은 호라이즌 일부만 실행이 정석(Diffusion Policy ~8/16). seed=0 고정으로
동일 50ep 위에서 16/8/4 페어 비교(에피소드 집합 통제, 정책 샘플링 노이즈만 잔존).

### H3 결과 (action_steps 스윕)

| action_steps | success_rate | any_pick | correct_color | 비고 |
|---|---|---|---|---|
| 16 (기존) | 0.32 (16/50) | 0.34 | 0.94 | open-loop 최대 = **최적** |
| 8 | 0.08 (4/50) | 0.08 | 1.00 | |
| 4 | 0.02 (1/50) | 0.02 | 1.00 | |

**판정: H3 반증.** 16→8→4 = any_pick 0.34→0.08→0.02 **단조 감소**(노이즈로 보기엔 너무
일관). action_steps↓일수록 나빠짐 → open-loop 드리프트가 범인이면 반대로 나와야 함.
실제로는 이 diffusion 정책이 **길게 commit할수록 좋고, 자주 재계획하면 매 replan마다 새
plan을 샘플링해 동작 일관성을 잃어 grasp 실패**(diffusion jitter). ⇒ **16(=호라이즌 최대)이
이미 최적**, 실행 주기로는 못 고침. reaching 병목 = **H3b(모델 정밀도)** 확정. (색은
4/4·1/1 = 100% → H2 반증 재확인.)

### 검증 트랙 — "reaching 부정확"이 진짜냐 (무과금; 이야기판은 eval-investigation-log §3)

| Test | 무엇 | 결과 |
|---|---|---|
| **2** 평가 경로 정직성 | 기록 절대-EEF 액션을 롤아웃과 동일 디코드(rot6d→quat→IK→step)로 모델없이 재생 | **재현율 1.000 (50/50)** → 디코드/프레임/IK 결백, **데이터 품질도 perfect** |
| **1** 빗나감 편향 vs 산포 | 실패 시 손−큐브 거리 분포 (방향벡터는 미기록→`miss_vec` 로깅 보강) | std 3.3cm, 0~13cm **넓은 산포** → 고정 오프셋(버그) 아님, **진짜 부정확** |

**결론: 8cm 빗나감은 측정 artifact 아닌 진짜 모델 한계.** 데이터 품질 perfect + 양 plateau →
**C 약함**, **B(warm-start full-tune)** 가 정당화된 다음 후보(언어 아닌 *액션 표현 용량* 확대).

## 7. 마지막 검토 — 공식 튜토리얼이 말하는 카메라 (2026-06-29)

진단 후 처방을 확정하기 전, NVIDIA 공식 + 커뮤니티 GR00T 파인튜닝 가이드를 정독해
"우리 세팅이 표준과 어디서 갈리나"를 무과금으로 확인.

| 항목 | 공식 권장 | 우리 |
|---|---|---|
| **카메라** | **손목(그리퍼) + 정면 2개** (Seeed: "손목에 1개, 책상 위에 1개 권장"; NVIDIA 예제 wrist+front 640×480) | **고정 base_camera 1개뿐** |
| 파인튜닝 범위 | 기본 = 액션 헤드+projector만 (비전·LLM frozen); `tune_visual`은 선택 | 동일 (head-only) |
| 정규화 레시피 | state dropout + color jitter로 정책이 비전에 의존하게 | (GR00T 내부 동일) |
| LR / 스텝 / batch | 1e-5 / 10k~20k / 16~32 | 20k / batch 16 — **같은 급** |

**결정적 발견**: 공식 정밀 레시피는 **손목 카메라**를 쓴다. 우리 병목(단일 고정 카메라로
큐브 3D 위치를 정밀하게 못 잡음)은 정확히 손목 카메라가 푸는 문제 — 그리퍼가 다가갈수록
큐브를 코앞에서 봐 깊이 모호성을 제거한다. → 처방이 두 갈래로 갈림:

- **B (visual 해동 warm-start)** — 같은 카메라 1개로 frozen "눈"만 녹여 짜냄. 싸고 빠름(서버
  재학습 1회). 단 단일 고정 캠의 **깊이 모호성은 구조적으로 남아** 천장이 낮을 위험.
- **D (손목 카메라 추가)** — `custom_envs` 에 wrist cam(panda hand camera) 추가 → 데이터
  재생성 → 재학습. 일은 더 많지만 **NVIDIA 표준 정밀 레시피와 정렬 = 근본 처방**. reaching
  정밀도 천장 자체를 올린다.

판단: 진단(=단일 고정 카메라 한계)과 가장 정합하는 건 **D**. B는 한계를 못 넘을 위험.
다만 D는 데이터 파이프라인(custom_envs 카메라 계약 + h5_to_lerobot video 키)을 손봐야 함.
→ 사용자 결정 대기.

출처: [NVIDIA SO-101 포스트트레이닝 블로그](https://huggingface.co/blog/nvidia/gr00t-n1-5-so101-tuning) ·
[Seeed 단일팔 GR00T 튜토리얼](https://wiki.seeedstudio.com/fine_tune_gr00t_n1.5_for_lerobot_so_arm_and_deploy_on_jetson_thor/)

---

> AI 협업 교훈(위 표의 B·C·"무과금"을 내가 틀렸다가 정정한 과정 + 재발 방지 지시
> 패턴)은 별도 문서로 분리했다 → `ai-collaboration-feedback.md`.
