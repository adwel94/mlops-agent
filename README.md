# ManiSkill 하네스 (Windows)

[ManiSkill3](https://www.maniskill.ai) 위에서 VLA(Vision-Language-Action) 학습용 데이터셋을 만드는 Windows용 하네스.

핵심 개념 두 개로 요약된다 — **환경 = task**, **행동 = .h5**.

```
task 환경  →  행동 궤적(.h5)  →  이미지 입힌 데이터셋(.h5)  →  품질 리포트 / 뷰어로 확인
```

task 환경에서 로봇 팔의 행동 궤적(.h5)을 만들고, 거기에 카메라 이미지를 입혀 (이미지 + 액션) 데이터셋을 자동으로 만들어주며, 결과를 품질 리포트·뷰어로 확인할 수 있다. 각 작업은 **슬래시 커맨드 / Python 함수 / CLI / Jupyter 노트북** 어느 방식으로든 동일하게 호출 가능.

## 무엇을 할 수 있나

- 행동 궤적(.h5) 얻기 — 공식 데모를 한 줄로 **받아오거나**(`fetch_sample_h5`), 모션 플래닝으로 **직접 생성**(`task_to_h5`)
- 그 궤적을 리플레이하면서 카메라 이미지를 입힌 데이터셋 자동 생성 (N 에피소드 배치, 재현율 출력, `h5_add_images`)
- 랜덤 에피소드를 뽑아 (메타 + 필름스트립 + mp4) 품질 리포트(Markdown) 생성 — 학습 전 데이터 점검 (`h5_report`)
- SAPIEN 데스크탑 뷰어로 환경 둘러보기(`view_task`) 또는 저장된 에피소드 재생(`replay_h5`)
- 설치/환경이 정상인지 헬스체크 (`check_maniskill_env`)

## 동작 구조

```
① 행동 궤적(.h5) 만들기 — 택1
   fetch_sample_h5   공식 데모 다운로드 (빠름/베이스라인)   ┐
   task_to_h5        모션 플래닝으로 직접 생성 (WSL)         ┘ → data/datasets/<task>/*.h5
        ↓
② h5_add_images      리플레이하며 카메라 이미지 입힘 → 데이터셋 → h5_report / view_task / replay_h5
```

핵심: 행동을 어디서 얻었든(받아오든 직접 풀든) 결과가 같은 형식이라 ② 이후 단계는 전부 공유된다. 두 방법 모두 `data/datasets/<task>/` 에 떨구므로 외부 의존도 없다.

## 빠른 시작

요구 사항: Windows + conda. `task_to_h5`(직접 생성)를 쓰려면 추가로 WSL (아래 "WSL 환경 준비").

```cmd
:: ① 행동 궤적 얻기 — 방법 A: 공식 데모 받아오기 (1회, 약 30 MB)
python scripts\fetch_sample_h5.py --task PickCube-v1

:: ① 행동 궤적 얻기 — 방법 B: 직접 생성 (WSL 구동, 약 0.2초/에피소드)
python scripts\task_to_h5.py --task PickCube-v1 --count 100

:: ② 궤적을 리플레이해 이미지 + 액션 데이터셋 생성 (약 50초)
::    기본 입력은 task_to_h5 출력(motionplanning.h5).
::    fetch 궤적을 쓰려면 --traj-path data\datasets\PickCube-v1\trajectory.h5
python scripts\h5_add_images.py --task PickCube-v1 --count 100

:: ③ 랜덤 3개 에피소드 품질 리포트 생성 (MD + 필름스트립 + mp4, data\...\reports\ 에 저장)
python scripts\h5_report.py --traj-path data\datasets\PickCube-v1\motionplanning.rgb.pd_joint_pos.physx_cpu.h5 --n 3

:: ③ 또는 데스크탑 뷰어로 재생
python scripts\replay_h5.py --traj-path data\datasets\PickCube-v1\motionplanning.h5 --episode 0
```

Claude Code 안에서는 위 단계가 그대로 슬래시 커맨드: `/fetch_sample_h5`, `/task_to_h5`, `/h5_add_images`, `/h5_report`, `/view_task`, `/replay_h5`, `/check_maniskill_env`.

## 일곱 가지 스킬과 호출 방식

| 스킬 | 슬래시 | Python 함수 | CLI |
|---|---|---|---|
| 데모 궤적 받기 | `/fetch_sample_h5` | `from scripts.fetch_sample_h5 import run` | `python scripts/fetch_sample_h5.py --task ...` |
| 행동 직접 생성 | `/task_to_h5` | `from scripts.task_to_h5 import run` | `python scripts/task_to_h5.py --task ... --count ...` |
| 데이터셋 생성 | `/h5_add_images` | `from scripts.h5_add_images import run` | `python scripts/h5_add_images.py --task ... --count ...` |
| 품질 리포트 | `/h5_report` | `from scripts.h5_report import run` | `python scripts/h5_report.py --traj-path ... --n 3` |
| 환경 뷰어 | `/view_task` | `from scripts.view_task import run` | `python scripts/view_task.py --task ...` |
| 에피소드 재생 | `/replay_h5` | `from scripts.replay_h5 import run` | `python scripts/replay_h5.py --traj-path ... --episode ...` |
| 환경 헬스체크 | `/check_maniskill_env` | `from scripts.check_maniskill_env import run` | `python scripts/check_maniskill_env.py` |

각 스킬에는 대응하는 `notebooks/<skill>.ipynb`가 있어 파라미터와 사용법을 보여준다.

## WSL 환경 준비 (`task_to_h5` 전용)

`task_to_h5`는 모션 플래닝 솔버 `mplib`을 쓰는데, 이건 Linux 전용 바이너리만 있어 Windows 네이티브에선 설치가 안 된다. 그래서 `task_to_h5`만 WSL 안에서 돌리고, Windows 쪽이 이를 구동한다. (나머지 스킬은 전부 Windows에서 동작.)

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

`task_to_h5.py` 상단 상수(`WSL_DISTRO`, `WSL_PYTHON`, `WSL_VK_ICD`)가 위 경로/배포판을 가리킨다. 환경이 다르면 그 상수만 맞추면 됨.

## 프로젝트 구조

```
maniskill/
├── .claude/skills/        슬래시 커맨드 정의 (스킬별 SKILL.md)
├── scripts/               Python 스킬 모듈 (function + CLI)
│   ├── fetch_sample_h5.py
│   ├── task_to_h5.py
│   ├── h5_add_images.py
│   ├── h5_report.py             데이터셋 품질 리포트 (MD)
│   ├── h5_to_media.py           영상/그리드/필름스트립 렌더 라이브러리 (h5_report가 사용; 스킬 아님)
│   ├── view_task.py
│   ├── replay_h5.py
│   ├── check_maniskill_env.py
│   ├── custom_envs.py            커스텀 task 환경 (예: ThreeColoredCubes-v1)
│   ├── custom_solutions.py       커스텀 task 모션플래닝 솔루션 (WSL)
│   ├── _wsl_solve_wrapper.py     빌트인 task용 WSL 래퍼
│   └── _wsl_solve_custom.py      커스텀 task용 WSL 생성기
├── notebooks/             스킬별 사용 예제 (사용법 + 파라미터)
├── data/                  생성된 데이터셋/미디어 (gitignore, 재생성 가능)
│   └── datasets/<task>/
├── CLAUDE.md              Claude Code 세션용 운영 가이드
└── README.md              이 파일
```

**상태 분리 (자기 포함 / 재현 가능):**

- 이 하네스가 **만드는 모든 것** (행동 궤적, 데이터셋 HDF5, MP4, PNG) 은 출처와 무관하게 프로젝트 내부 `data/datasets/<task>/` 에 저장됨. `fetch_sample_h5`도 외부 캐시(`~/.maniskill`)에 받은 데모를 `data/`로 복사해 들여오므로, 소비 단계는 외부 의존이 없다. `task_to_h5`는 WSL에서 돌지만 `/mnt/c` 경유로 `data/`에 직접 출력.
- `data/` 는 `.gitignore` 대상 — 대용량이고 재생성 가능하므로 git엔 코드/레시피만 커밋됨. 다른 환경에서 `git clone → 환경 준비 → fetch_sample_h5|task_to_h5 → h5_add_images` 로 동일하게 재현.

## 데이터 포맷

`h5_add_images`가 만드는 HDF5는 `traj_<N>` 키로 에피소드를 갖고, 각 에피소드는 다음 구조:

```
traj_N/
├── actions               (T-1, 8) float32       # 7 관절 + 1 그리퍼
├── success               (T-1,) bool
├── obs/
│   ├── agent/
│   │   ├── qpos          (T, 9) float32
│   │   └── qvel          (T, 9) float32
│   ├── extra/                                    # 태스크별 신호 (환경의 _get_obs_extra 가 정의)
│   │   ├── tcp_pose      (T, 7) float32          # 엔드 이펙터 pose (위치 + 쿼터니언)
│   │   └── ...                                   # 예: ThreeColoredCubes 면 target_id, target_pose 등
│   ├── sensor_param/base_camera/
│   │   ├── intrinsic_cv  (T, 3, 3) float32
│   │   └── extrinsic_cv  (T, 3, 4) float32
│   └── sensor_data/base_camera/
│       └── rgb           (T, 128, 128, 3) uint8  # 이미지
└── env_states/                                   # 시뮬레이션 상태 (정확한 재현용)
```

기본 100 에피소드 배치 기준 약 40 MB. 행동 궤적(`trajectory.h5` / `motionplanning.h5`)은 위에서 `obs/`가 빠진 형태 — `actions` + `env_states`만(이미지 없음). `h5_add_images`가 이걸 리플레이해 `obs/`를 채운다.

`obs/extra` 에 들어가는 신호는 **환경이 정한다** (`_get_obs_extra`). 정수 라벨(예: `target_id`)을 쓰는 태스크는 그 정수→문자열 사전이 데이터셋 `.json` 사이드카에 `label_metadata` 로 기록돼, 데이터셋만으로 라벨을 해독할 수 있다.

## 출력 파일 명명 규칙

```
data/datasets/<task>/trajectory.h5                             # fetch_sample_h5 (받아온 데모)
data/datasets/<task>/motionplanning.h5                         # task_to_h5 (직접 생성)
data/datasets/<task>/<source-stem>.<obs>.<control>.<sim>.h5    # h5_add_images (이미지 포함)
```

데이터셋 출력의 접두사는 입력 궤적 stem을 따른다 — 받아온 데모 입력이면 `trajectory.rgb...`, 직접 생성 입력이면 `motionplanning.rgb...`. 출처가 파일명에 남는 셈. 같은 옵션으로 재실행하면 덮어씀.

## 지원 태스크

`task_to_h5`가 행동을 생성할 수 있는 빌트인 12개 (ManiSkill panda 모션플래닝 솔루션 제공):
`PickCube-v1`, `StackCube-v1`, `PegInsertionSide-v1`, `PlugCharger-v1`, `PushCube-v1`, `PullCube-v1`, `PullCubeTool-v1`, `LiftPegUpright-v1`, `StackPyramid-v1`, `PlaceSphere-v1`, `DrawTriangle-v1`, `DrawSVG-v1`.

커스텀: `ThreeColoredCubes-v1` (색 큐브 3개 중 시드로 정해진 하나를 집는 언어 지시형 task). 새 커스텀 task를 추가하는 법은 `CLAUDE.md`의 "커스텀 task 추가하기" 참고.

## 알려진 제약

- 시뮬과 렌더 모두 CPU 백엔드 — 작은 배치엔 충분하지만 대규모 병렬 생성은 외부 인프라가 필요.
- `task_to_h5`는 WSL + 소프트웨어 Vulkan(lavapipe) 위에서 돌아 GPU 가속이 없음 — 단일 태스크 데이터엔 충분하지만 대량 생성은 느림.
- 멀티오브젝트/언어 지시형 빌트인 태스크(PickClutterYCB 등)는 모션플래닝 솔루션 미제공 → 솔루션 직접 작성 필요.
- 텔레오퍼레이션(직접 조작)과 EE 공간 컨트롤 모드는 미지원 — `pinocchio` 의존성 필요한데 현재 환경에 미설치.
- 학습 자체는 이 하네스 범위 밖. 외부 GPU 인프라에서 진행하는 것을 전제로 함.
