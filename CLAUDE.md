# ManiSkill 하네스

[ManiSkill3](https://www.maniskill.ai) 위에 얹은 Windows용 데이터셋 생성 하네스. 로봇 팔의 액션 궤적을 **받아오거나(fetch) 직접 생성(solve)** 한 뒤, 리플레이로 (이미지 + 액션) 시퀀스 데이터셋을 만들고, 결과를 시각/구조 양쪽으로 검증할 수 있게 정리한 도구 모음.

여섯 가지 작업을 **슬래시 커맨드 / Python 함수 / CLI / 노트북** 네 가지 인터페이스에서 동일하게 호출할 수 있게 설계됨.

## 아키텍처: 공급원(producer) → 공유 파이프라인(consumer)

액션 궤적을 만드는 **공급원**은 둘이고, 그 뒤 단계는 출처와 무관하게 **하나로 수렴**한다.

```
공급원 (액션 궤적 = actions + env_states, 이미지 없음)
  fetch   공식 데모 다운로드 (빠름/베이스라인)      ┐
  solve   모션 플래닝으로 직접 생성 (WSL)          ┘
        ↓  같은 형식
공유 파이프라인
  generate  리플레이하며 RGB 관측 기록 → 데이터셋
  check     구조/통계 검증
  render    MP4 / PNG 추출
  live      데스크탑 뷰어
```

## 여섯 가지 스킬

| 슬래시 | 분류 | 기능 | 스크립트 |
|---|---|---|---|
| `/fetch` | 공급원 | Hugging Face에서 공식 데모 다운로드 (멱등) | `scripts/fetch.py` |
| `/solve` | 공급원 | 모션 플래닝으로 액션 궤적 직접 생성 (**WSL 구동**) | `scripts/solve.py` |
| `/generate` | 소비 | 액션 궤적을 리플레이해 RGB + 액션 HDF5 데이터셋 생성 | `scripts/generate.py` |
| `/check` | 소비 | 환경 헬스체크 또는 생성된 HDF5 구조 검증 | `scripts/check.py` |
| `/render` | 소비 | HDF5 → MP4 영상 / PNG 그리드 미리보기 추출 | `scripts/render.py` |
| `/live` | 소비 | SAPIEN 뷰어 창 열기 — 환경 둘러보기 또는 에피소드 리플레이 | `scripts/live.py` |

Python 함수 진입점:

| 모듈 | 함수 |
|---|---|
| `scripts.fetch` | `run(task, force=False)` |
| `scripts.solve` | `run(task, count, traj_name, obs_mode, sim_backend, only_success, ...)` |
| `scripts.generate` | `run(task, count, obs_mode, target_control_mode, num_envs, traj_path, ...)` |
| `scripts.check` | `install()`, `dataset(path)` |
| `scripts.render` | `video(traj, episode, ...)`, `preview(traj, n, ...)` |
| `scripts.live` | `browse(task, ...)`, `replay(traj, episode, ...)` |

각 스크립트는 `if __name__ == "__main__":` 진입점에 동등한 argparse CLI가 있음.

## 디렉토리 구조

```
maniskill/
├── .claude/skills/     슬래시 커맨드 정의 (SKILL.md per 스킬)
├── scripts/            Python 스킬 모듈 (function + CLI 이중 인터페이스)
│   └── _wsl_solve_wrapper.py   WSL 내부에서 실행되는 solve 래퍼 (Windows에서 직접 안 돎)
├── notebooks/          스킬별 테스트 노트북 (호출 패턴 예제 + smoke 검증)
├── data/               생성된 데이터셋/미디어 (gitignore, 재생성 가능)
│   └── datasets/<task>/
├── CLAUDE.md           이 파일
└── README.md           일반 소개
```

상태 분리 원칙 (자기 포함 / 재현 가능):

- **데모 (입력)** — `fetch`가 받는 공식 데모는 ManiSkill 기본 캐시 `~/.maniskill/demos/<task>/` (프로젝트 밖). 외부 다운로드물이고 `/fetch`로 언제든 재생성되므로 프로젝트 밖에 둬도 재현성에 문제 없음.
- **생성물 (출력)** — `solve`가 만든 액션 궤적, `generate`가 만든 데이터셋, `render`가 만든 MP4/PNG는 **모두 프로젝트 내부 `data/`** 에 저장됨. 외부 데모 폴더는 절대 오염시키지 않음. (`solve`는 WSL에서 돌지만 `/mnt/c`를 통해 프로젝트 내부 `data/`로 직접 출력.)
- **환경 (전제조건)** — Windows conda env와 WSL conda env는 둘 다 프로젝트 밖이지만, 문서의 레시피로 재현 가능한 전제조건이라 자기 포함 원칙 위배가 아님 (코드/데이터가 아니라 실행 환경).
- `data/` 는 gitignore 대상 — 대용량이고 `git clone → 환경 준비 → /fetch|/solve → /generate` 로 재생성 가능하므로 git엔 *레시피*만 들어가고 데이터 자체는 안 들어감.

## 환경 가정

### Windows (소비 파이프라인 + solve 오케스트레이션)
- Windows 11 + NVIDIA GPU
- conda env: `maniskill`
- Python 실행 경로: `C:\Users\hun41\miniconda3\envs\maniskill\python.exe`
- 시뮬과 렌더 모두 **CPU 백엔드** (`sim_backend='cpu'`, `render_backend='cpu'`)
- 주요 패키지: `mani_skill 3.0.1`, `sapien 3.0.3`, `torch 2.12.0+cpu`, `jupyter`, `imageio[ffmpeg]`, `h5py`, `gymnasium`
- `pinocchio` 미설치 → EE 공간 컨트롤(`pd_ee_delta_pose`)과 텔레오퍼레이션 미지원.

### WSL (solve 액션 생성 전용)
- 배포판: `Ubuntu-22.04` (WSL2)
- Miniconda + `maniskill` env (Python 3.10): `torch 2.12.0+cpu`, `mani_skill 3.0.1`, `sapien 3.0.3`, `mplib 0.1.1`, `numpy<2`
- WSL Python 경로: `/root/miniconda3/envs/maniskill/bin/python`
- **소프트웨어 Vulkan**: `mesa-vulkan-drivers` (lavapipe). WSL엔 GPU Vulkan이 없어 sapien이 씬을 못 띄우므로 lavapipe ICD(`/usr/share/vulkan/icd.d/lvp_icd.x86_64.json`)로 우회.
- 이 값들은 `scripts/solve.py` 상단 상수(`WSL_DISTRO`, `WSL_PYTHON`, `WSL_VK_ICD`)에 박혀 있음.

`mplib`은 Linux 전용 바이너리(manylinux 휠)만 있어 Windows 네이티브에선 설치 불가 → 그래서 `solve`만 WSL에서 돈다.

## 데이터 흐름

```
# 공급원 (택1)
/fetch <task>                          # Hugging Face → ~/.maniskill/demos/<task>/motionplanning/trajectory.h5
/solve <task> <count>                  # WSL 모션플래닝 → data/datasets/<task>/motionplanning.h5
        ↓ 액션 궤적 (pd_joint_pos, obs_mode=none, 이미지 없음)
# 소비 (공유)
/generate <task> <count>               # CPU 시뮬에서 리플레이하며 관측 새로 기록
   [--traj-path ...]                   #   solve 산출물을 입력으로 쓰려면 경로 지정
        ↓ trajectory.<obs>.<ctrl>.<sim>.h5  (생성된 데이터셋)
/check dataset <hdf5>                  # 구조/통계 자동 검증
/render video|preview <hdf5> ...       # 영상/이미지 추출 (파일 출력)
/live browse|replay <task|hdf5> ...    # 데스크탑 뷰어 창
```

`generate`의 기본 입력은 `fetch`가 받아둔 데모. `solve` 산출물(`data/datasets/<task>/motionplanning.h5`)을 쓰려면 `--traj-path`(또는 함수 `traj_path=...`)로 명시.

## 출력 파일 명명 규칙

`solve` 산출물 (액션만, 원본 궤적):
```
data/datasets/<task>/motionplanning.h5   (+ .json)
```

`generate` 산출물 (RGB 데이터셋) — 접두사는 **입력 궤적의 stem**을 따름 (출처 기록):
```
data/datasets/<task>/<source-stem>.<obs_mode>.<control_mode>.<sim_backend>.h5
```
예: fetch 데모(`trajectory.h5`) 입력 → `trajectory.rgb.pd_joint_pos.physx_cpu.h5`; solve 산출물(`motionplanning.h5`) 입력 → `motionplanning.rgb.pd_joint_pos.physx_cpu.h5`. 같은 옵션으로 재실행하면 덮어씀.

내부 동작:
- `generate`: `replay_trajectory`가 입력 옆에 쓴 파일을 `data/datasets/<task>/` 로 이동.
- `solve`: WSL의 `run.py`가 `<record-dir>/<task>/motionplanning/<name>.h5` 구조로 쓰는 걸, `solve.py`가 `data/datasets/<task>/<name>.h5` 로 평탄화 이동 후 빈 서브디렉토리 정리.

## solve가 지원하는 태스크

ManiSkill이 panda 모션플래닝 솔루션을 제공하는 12개만 가능:
`PickCube-v1`, `StackCube-v1`, `PegInsertionSide-v1`, `PlugCharger-v1`, `PushCube-v1`, `PullCube-v1`, `PullCubeTool-v1`, `LiftPegUpright-v1`, `StackPyramid-v1`, `PlaceSphere-v1`, `DrawTriangle-v1`, `DrawSVG-v1`.

멀티오브젝트/언어 지시형(PickClutterYCB 등)은 솔루션 미제공 → 솔루션 스크립트 직접 작성 필요 (현재 범위 밖). `fetch`는 별도의 데모 배포 목록을 따름 (겹치지만 동일하진 않음).

## 코드 작성 시 유지해야 할 부분

- `scripts/generate.py`와 `scripts/live.py`의 `gym.make` monkey-patch — `render_backend='cpu'` 기본값 주입. Windows GPU 렌더 경로가 동작 불가능하므로 이 우회 필요.
- `scripts/_wsl_solve_wrapper.py`의 세 우회 — ① `render_backend='cpu'` 주입 ② `RenderSystem` 실패 시 인자 없이 재호출(llvmpipe 자동 선택) ③ 호출자(`solve.py`)의 `VK_ICD_FILENAMES`=lavapipe. WSL headless 동작의 핵심.
- `scripts/generate.py`의 `if __name__ == "__main__":` 가드 — Windows multiprocessing은 `spawn` 방식이라 가드가 없으면 자식 프로세스가 무한 spawn 루프에 빠짐.
- `scripts/solve.py`의 subprocess는 `encoding='utf-8', errors='replace'` 필수 — WSL이 UTF-8(tqdm 유니코드)을 뱉는데 Windows 기본 cp949로 디코드하면 깨짐.
- 함수 인터페이스와 CLI 인터페이스의 동등성 — 새 옵션 추가 시 양쪽에 일관되게 반영.
