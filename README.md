# ManiSkill 하네스 (Windows)

[ManiSkill3](https://www.maniskill.ai) 위에서 VLA(Vision-Language-Action) 학습용 데이터셋을 생성하는 Windows용 하네스. 공식 데모를 받아 리플레이하면서 (RGB 카메라 + 액션) 시퀀스 HDF5를 자동으로 만들어주고, 결과를 시각/구조 양쪽으로 검증할 수 있는 도구 모음.

## 무엇을 할 수 있나

- 한 줄로 임의의 ManiSkill 태스크 데모 받기
- 받아온 데모를 리플레이하면서 RGB 관측을 포함한 데이터셋 자동 생성 (N 에피소드 배치)
- 생성된 데이터셋의 구조/성공률 자동 검증
- 한 에피소드를 MP4로 추출하거나 여러 에피소드의 프레임 그리드 이미지 생성
- SAPIEN 데스크탑 뷰어로 태스크 환경 둘러보기 또는 저장된 에피소드 재생

각 작업은 **슬래시 커맨드 / Python 함수 / CLI / Jupyter 노트북** 어느 방식으로든 동일하게 호출 가능.

## 빠른 시작

요구 사항: Windows + conda. `maniskill` 환경에 `mani_skill 3.x`, `sapien`, `torch (cpu)`, `jupyter`, `imageio[ffmpeg]`, `h5py`, `gymnasium`이 설치돼 있어야 함.

```cmd
:: 1. 태스크 데모 다운로드 (1회, 약 30 MB)
python scripts\setup.py --task PickCube-v1

:: 2. 100 에피소드 RGB + 액션 데이터셋 생성 (약 50초)
python scripts\generate.py --task PickCube-v1 --count 100

:: 3. 생성물 검증 (출력은 프로젝트 내부 data/ 에 저장됨)
python scripts\check.py --dataset data\datasets\PickCube-v1\trajectory.rgb.pd_joint_pos.physx_cpu.h5

:: 4. 0번 에피소드 MP4로 추출
python scripts\render.py video --traj-path data\datasets\PickCube-v1\trajectory.rgb.pd_joint_pos.physx_cpu.h5 --episode 0

:: 5. 또는 데스크탑 뷰어로 재생
python scripts\live.py replay --traj-path data\datasets\PickCube-v1\trajectory.rgb.pd_joint_pos.physx_cpu.h5 --episode 0
```

Claude Code 안에서는 위 다섯 단계가 그대로 슬래시 커맨드: `/setup`, `/generate`, `/check`, `/render`, `/live`.

## 다섯 가지 스킬과 세 가지 호출 방식

| 스킬 | 슬래시 | Python 함수 | CLI |
|---|---|---|---|
| 데모 다운로드 | `/setup` | `from scripts.setup import run` | `python scripts/setup.py --task ...` |
| 데이터셋 생성 | `/generate` | `from scripts.generate import run` | `python scripts/generate.py --task ... --count ...` |
| 헬스/구조 체크 | `/check` | `from scripts.check import install, dataset` | `python scripts/check.py --install` / `--dataset PATH` |
| 미디어 추출 | `/render` | `from scripts.render import video, preview` | `python scripts/render.py video\|preview ...` |
| 데스크탑 뷰어 | `/live` | `from scripts.live import browse, replay` | `python scripts/live.py browse\|replay ...` |

각 스킬에는 대응하는 `notebooks/<skill>.ipynb`가 있어, 함수 호출과 subprocess 호출 두 패턴을 모두 보여주는 예제이자 회귀 검증으로 사용 가능.

## 프로젝트 구조

```
maniskill/
├── .claude/skills/        슬래시 커맨드 정의
│   ├── setup/SKILL.md
│   ├── generate/SKILL.md
│   ├── check/SKILL.md
│   ├── render/SKILL.md
│   └── live/SKILL.md
├── scripts/               Python 스킬 모듈 (function + CLI)
│   ├── setup.py
│   ├── generate.py
│   ├── check.py
│   ├── render.py
│   └── live.py
├── notebooks/             스킬별 사용 예제 / 회귀 검증
│   ├── setup.ipynb
│   ├── generate.ipynb
│   ├── check.ipynb
│   ├── render.ipynb
│   └── live.ipynb
├── data/                  생성된 데이터셋/미디어 (gitignore, 재생성 가능)
│   └── datasets/<task>/
├── CLAUDE.md              Claude Code 세션용 운영 가이드
└── README.md              이 파일
```

**상태 분리 (자기 포함 / 재현 가능):**

- 데모 (입력) 는 ManiSkill 기본 경로 `~/.maniskill/demos/<task>/` (프로젝트 외부)에 받아짐. 외부 다운로드물이고 `/setup`으로 언제든 재생성 가능.
- 이 하네스가 **생성하는 모든 것** (데이터셋 HDF5, MP4, PNG) 은 프로젝트 내부 `data/` 에 저장됨. 외부 데모 폴더는 건드리지 않음.
- `data/` 는 `.gitignore` 대상 — 대용량이고 재생성 가능하므로 git엔 코드/레시피만 커밋됨. 다른 환경에서 `git clone → /setup → /generate` 로 동일하게 재현.

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

## 출력 파일 명명 규칙

`/generate`가 만든 데이터셋은 원본과 같은 디렉토리에 다음 형식으로 저장:

```
trajectory.<obs_mode>.<control_mode>.<sim_backend>.h5
```

예: `trajectory.rgb.pd_joint_pos.physx_cpu.h5`. 같은 옵션으로 재실행하면 덮어씀.

## 알려진 제약

- 시뮬과 렌더 모두 CPU 백엔드 — 작은 배치엔 충분하지만 대규모 병렬 생성은 외부 인프라가 필요.
- 텔레오퍼레이션(직접 조작)과 EE 공간 컨트롤 모드는 미지원 — `pinocchio` 의존성이 필요한데 현재 환경에 미설치.
- 학습 자체는 이 하네스 범위 밖. 외부 GPU 인프라에서 진행하는 것을 전제로 함.
