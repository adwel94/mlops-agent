---
name: replay_h5
description: 저장된 궤적 HDF5의 한 에피소드 액션을 SAPIEN 데스크탑 뷰어 창에서 라이브 재생. 창은 채팅 안이 아니라 별도 OS 프로세스로 뜸. 녹화된 에피소드에서 로봇이 실제로 무엇을 하는지 눈으로 볼 때 사용. 씬만 둘러보려면 view_task 사용. args는 `<hdf5-경로> [에피소드]` 로 파싱 (경로 필수 — 옆에 .json 사이드카 필요).
---

# replay_h5 — 저장된 에피소드 뷰어 재생

`scripts/replay_h5.py` 래퍼. 백그라운드 subprocess를 spawn해 뷰어를 띄움; 사용자는 창 X 버튼으로 닫거나 반환된 pid를 terminate.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 토큰: HDF5 경로 (필수 — 마땅한 기본값 없음)
   - 두 번째 토큰: 에피소드 인덱스 (기본 `0`)
   - 옵션 `--shader default|rt-fast|rt|minimal` (기본 `default`)
2. 프로젝트 루트에서 **백그라운드 spawn** (채팅 안에서 블로킹 대기 금지):
   ```
   # Windows (PowerShell): Start-Process -NoNewWindow <maniskill-python> -ArgumentList "scripts/replay_h5.py","--traj-path","<PATH>","--episode","<N>"
   # macOS/Linux (백그라운드):  <maniskill-python> scripts/replay_h5.py --traj-path <PATH> --episode <N> &
   ```
3. spawn된 pid를 보고.

## 실제 동작

- `<PATH>` 옆 `.json` 사이드카에서 env_id/control_mode/해당 에피소드 시드를 읽어 env를 재구성하고, HDF5의 액션 배열을 한 step씩 재생하며 `render_human()` 호출. 마지막 액션 후 사용자가 창 닫을 때까지 최종 자세 유지.
- `sim_backend='cpu'` + `render_backend='cpu'` — Windows 친화 경로.

## 참고 및 주의

- 입력은 `task_to_h5`/`fetch_sample_h5` 의 원본 궤적이나 `h5_add_images` 산출물 어느 쪽도 가능 — `.json` 사이드카에 episodes/시드가 있으면 됨.
- 뷰어는 별도 데스크탑 창. 레이트레이싱 셰이더는 크래시 이력으로 피할 것.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/replay_h5 data/datasets/PickCube-v1/trajectory.h5` | 0번 에피소드 재생 |
| `/replay_h5 data/datasets/PickCube-v1/motionplanning.h5 5` | 5번 에피소드 재생 |
| `/replay_h5 data/datasets/ThreeColoredCubes-v1/motionplanning.h5 0` | 색 큐브 집기 0번 재생 |
