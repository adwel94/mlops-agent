---
name: generate
description: 한 태스크의 ManiSkill 모션 플래닝 데모를 Windows CPU 시뮬에서 리플레이해 VLA 학습용 데이터셋(RGB 프레임 + 액션 HDF5)을 생성. 로봇 매니퓰레이션 태스크의 학습 데이터를 만들 때 사용. args는 `[태스크-ID] [에피소드-수]` + 옵션 플래그 형식; 비어있으면 `PickCube-v1 100` 기본값. 해당 태스크의 setup이 선행되어 있어야 함 — 데모를 못 찾으면 사용자에게 먼저 `/setup <태스크>` 를 실행하라고 알릴 것.
---

# Generate 스킬 — VLA 데이터셋 생성

이 프로젝트의 `scripts/generate.py` 래퍼. 공식 `pd_joint_pos` 데모를 Windows에 친화적인 CPU 시뮬/렌더 경로로 리플레이하면서 요청한 관측/컨트롤 모드로 새 HDF5에 기록한다.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 비-플래그 토큰 = 태스크 ID (기본 `PickCube-v1`)
   - 두 번째 정수 토큰 = 에피소드 수 (기본 `100`)
   - 옵션 `--obs-mode <mode>` (기본 `rgb`)
   - 옵션 `--target-control-mode <mode>` (기본: 원본 `pd_joint_pos` 유지)
   - 옵션 `--num-envs <N>` (기본 `1`. >1이면 Windows multiprocessing 워커가 spawn됨 — 스크립트의 가드가 처리)
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\generate.py --task <TASK> --count <N> [--obs-mode rgb] ...
   ```
3. 스크립트가 출력한 결과 경로 (`Generated dataset -> ...`) 그대로 사용자에게 보여주기. 이 머신에서 obs-mode=rgb, num-envs=1 기준 대략 에피소드당 0.5초.

## 사전 체크 및 주의사항

- `~/.maniskill/demos/<task>/motionplanning/trajectory.h5` 가 없으면 스크립트가 `FileNotFoundError` 발생. 그 경우 재시도 말고 사용자에게 먼저 `/setup <태스크>` 실행 안내.
- `--target-control-mode pd_ee_delta_pose` 는 환경에 `pinocchio` 미설치라 막힘. 그 모드는 사용 금지; 기본 `pd_joint_pos` 사용.
- 출력 파일 명명: 원본과 같은 디렉토리에 `trajectory.<obs>.<ctrl>.<sim>.h5`. 같은 옵션으로 재실행하면 덮어씀.
- `scripts/generate.py` 자체가 `gym.make`을 monkey-patch해서 `render_backend='cpu'` 를 강제 주입 — Windows의 CUDA-Vulkan interop 세그폴트를 회피하는 핵심 우회.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/generate` | PickCube-v1 100 에피소드, RGB 관측 |
| `/generate StackCube-v1 50` | StackCube-v1 50 에피소드, RGB 관측 |
| `/generate PickCube-v1 200 --num-envs 4` | 200 에피소드, 4-way 병렬 |
