# ee_verify — EE-델타 액션이 sim에서 성공을 재현하는지 검증 (WSL)

`scripts/ee_verify.py` 래퍼. 이미지 데이터셋(`h5_add_images` 출력)의 기록된 관절 궤적을 7d 상대 엔드이펙터(EE-델타)로 변환(`scripts/ee_convert.py`)한 뒤, **랜덤 N개 에피소드**를 골라 매 스텝 **mplib IK** 로 풀어 sim에서 재생하며 **성공이 그대로 재현되는지** 확인한다. EE 분기의 **방법 게이트** — LeRobot로 포장(`h5_to_lerobot`)하기 전에 "EE+IK 방식이 이 task에서 통하는지" 먼저 확정한다.

> 검증 수단은 7d **델타** 표현(IK로 따라가지는지 보기 좋음)이지만, `h5_to_lerobot`이 저장하는 건 **절대 EEF**(GR00T가 내부 상대화) — 같은 궤적의 두 표현이라 게이트 통과 = 저장 포맷도 신뢰.

mplib이 Linux 전용이라 실행은 WSL에서 돌고, 이 스킬이 Windows에서 구동한다 (`task_to_h5`와 동일 패턴). pinocchio는 **불필요** — mplib IK로 EE→관절 변환.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 토큰 = 데이터셋 HDF5 경로 (`h5_add_images` 출력 — `obs/extra/tcp_pose` 필요). **필수.**
   - 두 번째 정수 토큰 = 검증할 **랜덤 에피소드 수** (기본 `10`; `0` = 전체)
   - 옵션 `--seed N` (재현 가능한 랜덤 샘플), `--task <id>` (기본: 사이드카 `env_id`), `--sim-backend cpu`
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\ee_verify.py --traj-path "<PATH>" [--count N] [--seed S]
   ```
3. 결과 한 줄 보고: `orig_success=.../N ee_success=.../N reproduction_rate=... ik_fails=...`.
   - `reproduction_rate`가 1.0에 가까우면 EE 방식 건강 → `h5_to_lerobot` 진행.
   - 낮으면 EE 변환/IK 문제 — 포장 전에 원인 점검.

## 동작 / 주의사항

- **랜덤 샘플 게이트**: 변환은 결정론적이라 랜덤 N개가 재현되면 방식이 건강한 것으로 본다(전체 보장이 필요하면 `--count 0`). h5_to_lerobot은 통과 후 **전체**를 변환한다(실패분 제외 필터링은 하지 않음 — 게이트 통과 = 방식 신뢰).
- **소스 h5에서만 동작**: 검증은 sim을 에피소드 초기 씬으로 reset해야 하는데, 그 초기상태(`episode_seed`)는 소스 데이터셋 h5에만 있고 LeRobot 출력엔 없다. 그래서 ee_verify는 **포장 전** 단계이며 LeRobot 데이터셋을 읽지 않는다.
- **전제조건: WSL 환경** (mplib + 소프트웨어 Vulkan). 미설치면 그 안내와 함께 실패 (README "WSL 환경 준비").
- 입력은 `--obs-mode rgb` 로 만들어진 데이터셋이어야 함 (`obs/extra/tcp_pose`, `obs/agent/qpos` 존재). 원본 `motionplanning.h5`(obs 없음)는 안 됨.
- 검증은 각 델타를 **기록된 tcp_pose 기준**으로 적용(기록 waypoint를 IK로 추종)해 성공을 본다 — 닫힌 루프 정책이 보정하는 open-loop 드리프트는 의도적으로 배제. IK 목표는 로봇 **base 프레임**으로 변환되어 들어감(실행기 내부 처리).
- 시뮬만 돌고 파일은 안 만든다 (순수 검증).

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/ee_verify data/datasets/ThreeColoredCubes-v1/motionplanning.rgb.pd_joint_pos.physx_cpu.h5` | 랜덤 10개 EE 재현 게이트 |
| `/ee_verify <hdf5> 5 --seed 42` | 재현 가능한 랜덤 5개 |
| `/ee_verify <hdf5> 0` | 전체 에피소드(완전 검증) |

보통 흐름: `/h5_add_images` → `/h5_report`(품질) → **`/ee_verify`(EE 게이트)** → `/h5_to_lerobot`(포장).
