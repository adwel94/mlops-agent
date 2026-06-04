---
name: task_to_h5
description: ManiSkill 모션 플래닝으로 로봇 팔의 액션 궤적을 처음부터 생성해 data/datasets/<task>/motionplanning.h5 로 저장 (다운로드가 아니라 직접 푼다). 결과는 액션 + env_states만 담긴 원본 궤적(이미지 없음)으로, 이후 h5_add_images가 리플레이하며 RGB를 입힌다. mplib(Linux 전용)이 필요해 실제 풀이는 WSL에서 돌고 이 스킬이 Windows에서 구동한다. args는 `[태스크-ID] [에피소드-수]` 형식; 비어있으면 `PickCube-v1 100`. 지원 태스크: PickCube/StackCube/PegInsertionSide/PlugCharger/PushCube/PullCube/PullCubeTool/LiftPegUpright/StackPyramid/PlaceSphere/DrawTriangle/DrawSVG/ThreeColoredCubes.
---

# task_to_h5 — 모션 플래닝으로 액션 궤적 생성

`scripts/task_to_h5.py` 래퍼. 액션을 모션 플래닝 솔버로 **직접 생성**한다. mplib이 Linux 전용이라 풀이는 WSL의 conda env에서 headless로 돌고, Windows 쪽이 이를 구동한 뒤 결과를 프로젝트 내부 `data/datasets/<task>/motionplanning.h5` 로 옮긴다.

흐름: `task_to_h5` → (원본 궤적: 액션+states, 이미지 없음) → `h5_add_images`(리플레이→RGB) → 데이터셋.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 비-플래그 토큰 = 태스크 ID (기본 `PickCube-v1`)
   - 두 번째 정수 토큰 = 에피소드 수 (기본 `100`)
   - 지원 목록 밖이면 스크립트가 `ValueError` — 사용자에게 지원 목록 안내.
2. 프로젝트 루트에서 실행 (PowerShell 툴, `Set-Location C:\Users\hun41\PycharmProjects\maniskill;` 후):
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\task_to_h5.py --task <TASK> --count <N>
   ```
3. 요약(`[task_to_h5] success_rate=...`)과 결과 경로(`Solved trajectory -> ...`) 그대로 보고. PickCube 기준 에피소드당 약 0.2~0.3초.

## 동작 원리 / 주의사항

- **전제조건: WSL 환경.** WSL Ubuntu-22.04 + Miniconda `maniskill` env + `mesa-vulkan-drivers`(lavapipe) 가 미리 설치돼 있어야 함 (README "WSL 환경 준비"). 안 돼 있으면 그 안내와 함께 실패.
- WSL엔 GPU Vulkan이 없어 **소프트웨어 Vulkan(llvmpipe)** 으로 렌더 디바이스를 띄움 (`VK_ICD_FILENAMES`=lavapipe + 래퍼의 `render_backend='cpu'` 주입/`RenderSystem` 폴백). 이게 WSL headless 동작의 핵심.
- 산출물은 `obs_mode=none`(이미지 없음). 학습용 RGB가 필요하면 이어서 `/h5_add_images <태스크> <count>` (기본 입력이 이 파일).
- `ThreeColoredCubes-v1` 같은 이 하네스의 커스텀 태스크는 `scripts/custom_solutions.py` 의 솔루션으로 풀림. 솔버 미지원 태스크(예: PickClutterYCB)는 솔루션 직접 작성 필요 — 현재 범위 밖.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/task_to_h5` | PickCube-v1 100개 액션 생성 |
| `/task_to_h5 ThreeColoredCubes-v1 50` | 색 큐브 집기 50개 생성 |
| `/task_to_h5 PegInsertionSide-v1 20` | PegInsertion 20개 |

이후 보통: `/task_to_h5 <태스크> <N>` → `/h5_add_images <태스크> <N>`.
