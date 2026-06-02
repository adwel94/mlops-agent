# ManiSkill 하네스 (Windows)

[ManiSkill3](https://www.maniskill.ai) 위에서 VLA(Vision-Language-Action) 학습용 데이터셋을 생성하는 Windows용 하네스. 로봇 팔의 액션 궤적을 **받아오거나(fetch) 직접 생성(solve)** 한 뒤, 리플레이하면서 (RGB 카메라 + 액션) 시퀀스 HDF5를 자동으로 만들어주고, 결과를 시각/구조 양쪽으로 검증할 수 있는 도구 모음.

## 무엇을 할 수 있나

- 공식 데모를 한 줄로 받아오기 (`fetch`), 또는 모션 플래닝으로 액션을 **직접 생성** (`solve`)
- 받은/만든 액션 궤적을 리플레이하면서 RGB 관측을 포함한 데이터셋 자동 생성 (N 에피소드 배치)
- 생성된 데이터셋의 구조/성공률 자동 검증
- 한 에피소드를 MP4로 추출하거나 여러 에피소드의 프레임 그리드 이미지 생성
- SAPIEN 데스크탑 뷰어로 태스크 환경 둘러보기 또는 저장된 에피소드 재생

각 작업은 **슬래시 커맨드 / Python 함수 / CLI / Jupyter 노트북** 어느 방식으로든 동일하게 호출 가능.

## 동작 구조: 공급원 → 공유 파이프라인

```
공급원 (액션 궤적 = 액션 + 상태, 이미지 없음)
  fetch   공식 데모 다운로드 (빠름/베이스라인)   ┐
  solve   모션 플래닝으로 직접 생성 (WSL)       ┘
        ↓ 같은 형식
공유 파이프라인
  generate  리플레이하며 RGB 기록 → 데이터셋 → check / render / live
```

핵심: 액션을 어디서 얻었든(받아오든 직접 풀든) 결과 형식이 같아서 `generate` 이후 단계는 전부 공유된다.

## 빠른 시작

요구 사항: Windows + conda (소비 파이프라인), 그리고 `solve`를 쓰려면 WSL (아래 "WSL 환경 준비").

```cmd
:: 공급원 A — 공식 데모 받아오기 (1회, 약 30 MB)
python scripts\fetch.py --task PickCube-v1

:: 공급원 B — 액션을 직접 생성 (WSL 구동, 약 0.2초/에피소드)
python scripts\solve.py --task PickCube-v1 --count 100

:: 2. 액션 궤적을 리플레이해 RGB + 액션 데이터셋 생성 (약 50초)
::    (solve 산출물을 쓰려면 --traj-path data\datasets\PickCube-v1\motionplanning.h5)
python scripts\generate.py --task PickCube-v1 --count 100

:: 3. 생성물 검증 (출력은 프로젝트 내부 data/ 에 저장됨)
python scripts\check.py --dataset data\datasets\PickCube-v1\trajectory.rgb.pd_joint_pos.physx_cpu.h5

:: 4. 0번 에피소드 MP4로 추출
python scripts\render.py video --traj-path data\datasets\PickCube-v1\trajectory.rgb.pd_joint_pos.physx_cpu.h5 --episode 0

:: 5. 또는 데스크탑 뷰어로 재생
python scripts\live.py replay --traj-path data\datasets\PickCube-v1\trajectory.rgb.pd_joint_pos.physx_cpu.h5 --episode 0
```

Claude Code 안에서는 위 단계가 그대로 슬래시 커맨드: `/fetch`, `/solve`, `/generate`, `/check`, `/render`, `/live`.

## 여섯 가지 스킬과 호출 방식

| 스킬 | 분류 | 슬래시 | Python 함수 | CLI |
|---|---|---|---|---|
| 데모 다운로드 | 공급원 | `/fetch` | `from scripts.fetch import run` | `python scripts/fetch.py --task ...` |
| 액션 직접 생성 | 공급원 | `/solve` | `from scripts.solve import run` | `python scripts/solve.py --task ... --count ...` |
| 데이터셋 생성 | 소비 | `/generate` | `from scripts.generate import run` | `python scripts/generate.py --task ... --count ...` |
| 헬스/구조 체크 | 소비 | `/check` | `from scripts.check import install, dataset` | `python scripts/check.py --install` / `--dataset PATH` |
| 미디어 추출 | 소비 | `/render` | `from scripts.render import video, preview` | `python scripts/render.py video\|preview ...` |
| 데스크탑 뷰어 | 소비 | `/live` | `from scripts.live import browse, replay` | `python scripts/live.py browse\|replay ...` |

각 스킬에는 대응하는 `notebooks/<skill>.ipynb`가 있어, 함수 호출과 subprocess 호출 두 패턴을 모두 보여주는 예제이자 회귀 검증으로 사용 가능.

## WSL 환경 준비 (`solve` 전용)

`solve`는 모션 플래닝 솔버 `mplib`을 쓰는데, 이건 Linux 전용 바이너리만 있어 Windows 네이티브에선 설치가 안 된다. 그래서 `solve`만 WSL 안에서 돌리고, Windows 쪽 `solve.py`가 이를 구동한다. (나머지 스킬은 전부 Windows에서 동작.)

1회 셋업 (WSL Ubuntu-22.04 안에서):

```bash
# 1) Miniconda 설치 + maniskill env (Python 3.10)
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh
bash ~/miniconda.sh -b -p ~/miniconda3
~/miniconda3/bin/conda create -n maniskill python=3.10 -y

# 2) 패키지 (Windows와 동일 버전 + mplib)
~/miniconda3/envs/maniskill/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
~/miniconda3/envs/maniskill/bin/pip install "mani_skill==3.0.1" mplib "numpy<2"

# 3) 소프트웨어 Vulkan (GPU 없는 WSL에서 sapien이 씬을 띄우려면 필요)
sudo apt-get update && sudo apt-get install -y mesa-vulkan-drivers
```

`solve.py` 상단 상수(`WSL_DISTRO`, `WSL_PYTHON`, `WSL_VK_ICD`)가 위 경로/배포판을 가리킨다. 환경이 다르면 그 상수만 맞추면 됨.

## 프로젝트 구조

```
maniskill/
├── .claude/skills/        슬래시 커맨드 정의 (fetch, solve, generate, check, render, live)
├── scripts/               Python 스킬 모듈 (function + CLI)
│   ├── fetch.py
│   ├── solve.py
│   ├── _wsl_solve_wrapper.py   WSL 내부에서 실행되는 solve 래퍼
│   ├── generate.py
│   ├── check.py
│   ├── render.py
│   └── live.py
├── notebooks/             스킬별 사용 예제 / 회귀 검증
├── data/                  생성된 데이터셋/미디어 (gitignore, 재생성 가능)
│   └── datasets/<task>/
├── CLAUDE.md              Claude Code 세션용 운영 가이드
└── README.md              이 파일
```

**상태 분리 (자기 포함 / 재현 가능):**

- 데모 (입력) 는 ManiSkill 기본 경로 `~/.maniskill/demos/<task>/` (프로젝트 외부)에 받아짐. 외부 다운로드물이고 `/fetch`로 언제든 재생성 가능.
- 이 하네스가 **생성하는 모든 것** (solve 액션 궤적, 데이터셋 HDF5, MP4, PNG) 은 프로젝트 내부 `data/` 에 저장됨. `solve`는 WSL에서 돌지만 `/mnt/c` 경유로 `data/`에 직접 출력 — 외부 데모 폴더는 건드리지 않음.
- `data/` 는 `.gitignore` 대상 — 대용량이고 재생성 가능하므로 git엔 코드/레시피만 커밋됨. 다른 환경에서 `git clone → 환경 준비 → /fetch|/solve → /generate` 로 동일하게 재현.

## 데이터 포맷

`/generate`가 만드는 HDF5는 `traj_<N>` 키로 에피소드를 갖고, 각 에피소드는 다음 구조:

```
traj_N/
├── actions               (T-1, 8) float32       # 7 관절 + 1 그리퍼
├── success               (T-1,) bool
├── obs/
│   ├── agent/
│   │   ├── qpos          (T, 9) float32
│   │   └── qvel          (T, 9) float32
│   ├── extra/
│   │   ├── tcp_pose      (T, 7) float32         # 엔드 이펙터 pose (위치 + 쿼터니언)
│   │   ├── goal_pos      (T, 3) float32
│   │   └── is_grasped    (T,) bool
│   ├── sensor_param/base_camera/
│   │   ├── intrinsic_cv  (T, 3, 3) float32
│   │   ├── extrinsic_cv  (T, 3, 4) float32
│   │   └── cam2world_gl  (T, 4, 4) float32
│   └── sensor_data/base_camera/
│       └── rgb           (T, 128, 128, 3) uint8
└── env_states/           # 시뮬레이션 상태 (정확한 재현용)
```

기본 100 에피소드 배치 기준 약 40 MB.

`solve` 산출물(`motionplanning.h5`)은 위에서 `obs/` 가 빠진 형태 — `actions` + `env_states` 만 (이미지 없음). `generate`가 이걸 리플레이해 `obs/`를 채운다.

## 출력 파일 명명 규칙

```
data/datasets/<task>/motionplanning.h5                          # solve 산출물 (액션만)
data/datasets/<task>/<source-stem>.<obs>.<control>.<sim>.h5     # generate 산출물 (RGB)
```

`generate` 출력의 접두사는 입력 궤적 stem을 따른다 — fetch 데모 입력이면 `trajectory.rgb...`, solve 산출물 입력이면 `motionplanning.rgb...`. 출처가 파일명에 남는 셈. 같은 옵션으로 재실행하면 덮어씀.

## solve가 지원하는 태스크

ManiSkill이 panda 모션플래닝 솔루션을 제공하는 12개:
`PickCube-v1`, `StackCube-v1`, `PegInsertionSide-v1`, `PlugCharger-v1`, `PushCube-v1`, `PullCube-v1`, `PullCubeTool-v1`, `LiftPegUpright-v1`, `StackPyramid-v1`, `PlaceSphere-v1`, `DrawTriangle-v1`, `DrawSVG-v1`.

## 알려진 제약

- 시뮬과 렌더 모두 CPU 백엔드 — 작은 배치엔 충분하지만 대규모 병렬 생성은 외부 인프라가 필요.
- `solve`는 WSL + 소프트웨어 Vulkan(lavapipe) 위에서 돌아 GPU 가속이 없음 — 단일 태스크 데이터엔 충분하지만 대량 생성은 느림.
- 멀티오브젝트/언어 지시형 태스크(PickClutterYCB 등)는 모션플래닝 솔루션 미제공 → 솔루션 직접 작성 필요 (현재 범위 밖).
- 텔레오퍼레이션(직접 조작)과 EE 공간 컨트롤 모드는 미지원 — `pinocchio` 의존성 필요한데 현재 환경에 미설치.
- 학습 자체는 이 하네스 범위 밖. 외부 GPU 인프라에서 진행하는 것을 전제로 함.
