---
name: live
description: SAPIEN 데스크탑 뷰어 창을 열어 시각 확인 — 새 태스크 씬을 둘러보거나, 저장된 HDF5의 한 에피소드를 라이브로 재생. 창은 채팅창 안이 아니라 별도 OS 프로세스로 뜸. 시뮬레이터를 시각적으로 보고 싶을 때 사용 — 태스크 레이아웃 관찰 또는 녹화된 에피소드를 프레임별로 재생. 텔레오퍼레이션(사용자가 직접 팔 조작)은 이 스킬에 없음 — `pinocchio` 의존성이 필요한데 미설치. args는 `browse [태스크]` 또는 `replay <hdf5-경로> [에피소드]` 로 파싱.
---

# Live 스킬 — SAPIEN 뷰어 창

`scripts/live.py` 래퍼. 백그라운드 subprocess를 spawn해 뷰어를 띄움; 사용자는 창의 X 버튼으로 닫거나, 반환된 pid를 terminate해서 종료.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 토큰: `browse` 또는 `replay` (필수)
   - `browse` 두 번째 토큰: 태스크 ID (기본 `PickCube-v1`)
   - `replay` 두 번째 토큰: HDF5 경로 (필수 — 마땅한 기본값 없음)
   - `replay` 세 번째 토큰: 에피소드 인덱스 (기본 `0`)
   - 옵션 `--shader default|rt-fast|rt|minimal` (기본 `default`; `rt`/`rt-fast`는 Windows에서 크래시 이력 있음)
2. 프로젝트 루트에서 실행:
   ```
   Start-Process -NoNewWindow C:\Users\hun41\miniconda3\envs\maniskill\python.exe -ArgumentList "scripts\live.py","browse","--task","<TASK>"
   ```
   또는 사용자가 명시적으로 대기를 원할 때만 (블로킹 호출):
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\live.py browse --task <TASK>
   ```
3. spawn된 pid를 사용자에게 보고 (필요시 종료할 수 있도록). 채팅 안에서 블로킹으로 대기하지 말 것 — 항상 spawn하고 즉시 반환.

## 실제 동작

- `browse <태스크>` : `gym.make(태스크, ...)` 환경을 reset 상태로 뷰어에 띄움. 로봇은 움직이지 않음; 사용자가 마우스로 카메라 회전하며 둘러보고 창 닫음.
- `replay <경로> <ep>` : `<ep>` 에피소드의 액션 배열을 읽어, 저장된 시드로 env를 재구성하고, 각 액션을 step하면서 `render_human()` 호출. 마지막 액션 후 사용자가 창 닫을 때까지 최종 자세 유지.
- 두 모드 모두 `sim_backend='cpu'` + `render_backend='cpu'` 사용 — Windows 친화 경로. CUDA-Vulkan interop 없음.

## 참고 및 주의

- 뷰어는 별도 데스크탑 창. 사용자는 실제 모니터를 봐야 함 (채팅 스크롤백이 아님).
- 기본 셰이더는 래스터화 (`default`). 레이트레이싱 셰이더 (`rt`, `rt-fast`)는 이 머신의 SAPIEN 뷰어에서 크래시 이력이 있어 명시 요청 없이는 피할 것.
- 텔레오퍼레이션(인터랙티브 팔 컨트롤)은 의도적으로 미포함 — `pinocchio` IK 라이브러리가 conda env에 없음. 사용자가 텔레오퍼레이션 요청하면 보류된 기능임을 알릴 것.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/live browse` | PickCube-v1 뷰어 열림, 로봇 정지 |
| `/live browse StackCube-v1` | StackCube-v1 뷰어 열림 |
| `/live replay C:\Users\...\trajectory.rgb.pd_joint_pos.physx_cpu.h5 0` | 0번 에피소드 재생 |
| `/live replay PATH 5` | 5번 에피소드 재생 |
