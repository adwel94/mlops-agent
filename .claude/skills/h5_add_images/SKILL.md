---
name: h5_add_images
description: 액션 궤적(.h5)을 Windows CPU 시뮬에서 리플레이하면서 카메라 이미지를 입혀 VLA 학습용 데이터셋(.h5)을 생성. fetch_sample_h5로 받은 궤적이든 task_to_h5로 생성한 궤적이든 출처와 무관하게 받는 공유 단계. 기본 입력은 data/datasets/<task>/motionplanning.h5 (task_to_h5 출력) — 없으면 사용자에게 먼저 task_to_h5(또는 fetch_sample_h5) 실행을 안내. args는 `[태스크-ID] [에피소드-수]` + 옵션 플래그; 비어있으면 `PickCube-v1 100`.
---

# h5_add_images — 궤적에 이미지 입혀 데이터셋 만들기

`scripts/h5_add_images.py` 래퍼. 원본 궤적을 Windows CPU 시뮬/렌더로 리플레이하면서 요청한 관측 모드(기본 RGB)로 새 HDF5에 기록한다. 두 공급원이 같은 자기기술(self-describing) 형식(액션+states+`.json` 사이드카)을 뱉으므로 이 단계는 출처를 몰라도 동일하게 동작 — `.json` 에서 env_id/control_mode 를 읽어 처리한다.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 비-플래그 토큰 = 태스크 ID (기본 `PickCube-v1`)
   - 두 번째 정수 토큰 = 에피소드 수 (기본 `100`)
   - 옵션 `--traj-path <PATH>` (기본: `data/datasets/<task>/motionplanning.h5`)
   - 옵션 `--obs-mode <mode>` (기본 `rgb`)
   - 옵션 `--num-envs <N>` (기본 `1`; >1이면 Windows multiprocessing 워커 spawn — 스크립트 가드가 처리)
2. 프로젝트 루트에서 실행:
   ```
   <maniskill-python> scripts/h5_add_images.py --task <TASK> --count <N> [--obs-mode rgb] [--traj-path <PATH>]
   ```
3. 결과 경로(`Generated dataset -> ...`) 그대로 보고. obs-mode=rgb, num-envs=1 기준 대략 에피소드당 0.5초.

## 사전 체크 및 주의사항

- 기본 입력은 `data/datasets/<task>/motionplanning.h5` (task_to_h5 출력). 없으면 `FileNotFoundError` — 재시도 말고 사용자에게 먼저 `/task_to_h5 <태스크>`(직접 생성) 또는 `/fetch_sample_h5 <태스크>`(데모 받기) 안내.
- fetch로 받은 궤적을 입력으로 쓰려면 `--traj-path data/datasets/<태스크>/trajectory.h5` 지정.
- 출력 이름은 **입력 stem** 을 따름: `motionplanning.h5` → `motionplanning.<obs>.<ctrl>.<sim>.h5`, `trajectory.h5` → `trajectory.<obs>...`. 같은 옵션 재실행 시 덮어씀.
- 환경이 `label_metadata()` 를 노출하면(예: ThreeColoredCubes의 `target_id → ["red","green","blue"]`), 그 정수→라벨 매핑이 출력 `.json` 사이드카에 자동 기록됨 — 데이터셋만으로 라벨 해독 가능. 노출 안 하는 태스크는 영향 없음.
- `--target-control-mode pd_ee_delta_pose` 는 `pinocchio` 미설치라 막힘. 기본 `pd_joint_pos` 사용.
- 스크립트가 `gym.make` 을 monkey-patch해 `render_backend='cpu'` 강제 — Windows CUDA-Vulkan interop 세그폴트 회피 핵심.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/h5_add_images` | PickCube-v1 100 에피소드, RGB (기본 입력 motionplanning.h5) |
| `/h5_add_images ThreeColoredCubes-v1 50` | 색 큐브 집기 50개 데이터셋 |
| `/h5_add_images PickCube-v1 3 --traj-path data/datasets/PickCube-v1/trajectory.h5` | fetch 데모를 입력으로 |
