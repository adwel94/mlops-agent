---
name: view_task
description: SAPIEN 데스크탑 뷰어 창을 열어 태스크 환경을 시각 확인. 창은 채팅 안이 아니라 별도 OS 프로세스로 뜸; 로봇은 움직이지 않고 사용자가 마우스로 카메라만 회전. 데이터 생성 전 태스크 씬/큐브 배치를 눈으로 볼 때 사용. 녹화된 에피소드를 재생하려면 replay_h5 사용. 텔레오퍼레이션(직접 팔 조작)은 없음 — pinocchio 미설치. args는 `[태스크-ID]` 로 파싱; 비어있으면 `PickCube-v1`.
---

# view_task — 태스크 환경 뷰어 창

`scripts/view_task.py` 래퍼. 백그라운드 subprocess를 spawn해 뷰어를 띄움; 사용자는 창 X 버튼으로 닫거나 반환된 pid를 terminate.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 토큰: 태스크 ID (기본 `PickCube-v1`)
   - 옵션 `--shader default|rt-fast|rt|minimal` (기본 `default`; `rt`/`rt-fast`는 이 머신 크래시 이력)
2. 프로젝트 루트에서 **백그라운드 spawn** (채팅 안에서 블로킹 대기 금지 — 항상 spawn 후 즉시 반환):
   ```
   Start-Process -NoNewWindow C:\Users\hun41\miniconda3\envs\maniskill\python.exe -ArgumentList "scripts\view_task.py","--task","<TASK>"
   ```
3. spawn된 pid를 보고 (필요시 종료용).

## 실제 동작

- `gym.make(태스크, ...)` 환경을 reset 상태로 뷰어에 띄움. 로봇은 정지; 사용자가 마우스로 카메라 회전하며 둘러보고 창 닫음.
- `sim_backend='cpu'` + `render_backend='cpu'` — Windows 친화 경로.

## 참고 및 주의

- 뷰어는 별도 데스크탑 창. 사용자는 실제 모니터를 봐야 함 (채팅 스크롤백 아님).
- 레이트레이싱 셰이더(`rt`, `rt-fast`)는 이 머신 SAPIEN 뷰어에서 크래시 이력 — 명시 요청 없이는 피할 것.
- 텔레오퍼레이션은 의도적 미포함 (`pinocchio` IK 미설치). 요청 시 보류된 기능임을 알릴 것.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/view_task` | PickCube-v1 뷰어 열림, 로봇 정지 |
| `/view_task ThreeColoredCubes-v1` | 색 큐브 씬 뷰어 열림 |
| `/view_task StackCube-v1` | StackCube-v1 뷰어 열림 |
