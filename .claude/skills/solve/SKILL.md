---
name: solve
description: ManiSkill 모션 플래닝으로 로봇 팔의 액션 궤적을 처음부터 생성 (다운로드가 아니라 직접 푼다). 결과는 액션 + env_states만 담긴 원본 궤적(이미지 없음)으로, 이후 generate가 리플레이하며 RGB를 입힌다. mplib(Linux 전용)이 필요해 실제 풀이는 WSL에서 돌고, 이 스킬은 Windows에서 그걸 구동한다. args는 `[태스크-ID] [에피소드-수]` 형식; 비어있으면 `PickCube-v1 100` 기본값. 지원 태스크는 PickCube/StackCube/PegInsertionSide/PlugCharger/PushCube/PullCube/PullCubeTool/LiftPegUpright/StackPyramid/PlaceSphere/DrawTriangle/DrawSVG.
---

# Solve 스킬 — 모션 플래닝으로 액션 직접 생성

이 프로젝트의 `scripts/solve.py` 래퍼. `fetch`가 공식 데모를 *받아오는* 반면, `solve`는 ManiSkill 모션 플래닝 솔버로 액션을 *직접 생성*한다. mplib이 Linux 전용이라 풀이는 WSL의 conda env에서 headless로 돌고, Windows 쪽 `solve.py`가 이를 구동한 뒤 결과를 프로젝트 내부 `data/datasets/<task>/motionplanning.h5` 로 옮긴다.

파이프라인 위치: `solve` → (원본 궤적: 액션+states, 이미지 없음) → `generate`(리플레이→RGB) → 데이터셋.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 비-플래그 토큰 = 태스크 ID (기본 `PickCube-v1`)
   - 두 번째 정수 토큰 = 에피소드 수 (기본 `100`)
   - 지원 태스크 목록 밖이면 스크립트가 `ValueError` — 사용자에게 지원 목록 안내.
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\solve.py --task <TASK> --count <N>
   ```
   PowerShell 툴 사용. `Set-Location C:\Users\hun41\PycharmProjects\maniskill;` 후 실행.
3. 스크립트가 출력한 요약(`success_rate=...`)과 결과 경로(`Solved trajectory -> ...`) 그대로 보여주기. 이 머신에서 PickCube 기준 에피소드당 약 0.2~0.3초.

## 동작 원리 / 주의사항

- **전제조건: WSL 환경.** WSL Ubuntu-22.04 + Miniconda `maniskill` env + `mesa-vulkan-drivers`(lavapipe) 가 미리 설치돼 있어야 함 (README "WSL 환경 준비"). 안 돼 있으면 스크립트가 그 안내와 함께 실패.
- 풀이는 GPU 없는 WSL에서 **소프트웨어 Vulkan(llvmpipe)** 으로 렌더 디바이스를 띄움. `solve.py`가 `VK_ICD_FILENAMES`를 lavapipe ICD로 지정하고, 래퍼(`scripts/_wsl_solve_wrapper.py`)가 `render_backend='cpu'` 주입 + `RenderSystem` 폴백 패치를 적용 — 이 세 가지가 WSL headless 동작의 핵심.
- 출력은 `obs_mode=none`(이미지 없음). 학습용 RGB가 필요하면 이어서 `/generate <task> <count>` 를 호출하거나, `generate.run(task, traj_path=...)` 에 이 파일 경로를 넘김.
- 솔버 미지원 태스크(예: PickClutterYCB, 언어 지시형)는 솔루션 스크립트를 직접 작성해야 함 — 현재 범위 밖.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/solve` | PickCube-v1 100개 액션 생성 |
| `/solve StackCube-v1 50` | StackCube-v1 50개 액션 생성 |
| `/solve PegInsertionSide-v1 20` | PegInsertion 20개 |

생성 후 보통 이어지는 흐름: `/solve PickCube-v1 100` → `/generate PickCube-v1 100` (단, generate가 solve 산출물을 입력으로 쓰게 하려면 `traj_path` 지정 필요).
