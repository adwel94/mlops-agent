# ManiSkill 하네스

[ManiSkill3](https://www.maniskill.ai) 위에 얹은 Windows용 VLA 데이터셋 생성 하네스. **task 환경**에서 로봇 팔의 **행동 궤적(.h5)** 을 만들고, 거기에 카메라 이미지를 입혀 **(이미지 + 액션) 데이터셋(.h5)** 을 만든 뒤, 품질 리포트·뷰어로 확인하는 도구 모음.

핵심 개념 두 개: **환경 = task**, **행동 = .h5**.

일곱 가지 스킬을 **슬래시 커맨드 / Python 함수 / CLI / 노트북** 네 인터페이스에서 동일하게 호출할 수 있게 설계됨.

## 흐름

```
① 행동 궤적(.h5) 만들기 — 택1
   fetch_sample_h5   공식 데모 다운로드 (빠름/베이스라인)   ┐
   task_to_h5        모션 플래닝으로 직접 생성 (WSL)         ┘ → data/datasets/<task>/*.h5
        ↓
② h5_add_images      궤적을 리플레이하며 카메라 이미지를 입힘 → 데이터셋 .h5
        ↓
③ 확인
   h5_report            랜덤 N개 에피소드 품질 리포트 (MD: 메타 + 필름스트립 + mp4)
   view_task            환경 뷰어 창 (씬 둘러보기)
   replay_h5            저장된 에피소드 뷰어 재생
   check_maniskill_env  환경 헬스체크 (전제조건 점검)
```

행동 궤적을 얻는 방법은 둘(받아오기 / 직접 생성)이지만, 둘 다 `data/datasets/<task>/` 에 같은 자기기술(self-describing) 형식으로 떨군다. 그래서 ② 이후 단계는 **출처를 몰라도 동일하게** 동작한다 (`.json` 사이드카에서 env_id·control_mode를 읽음).

## 일곱 가지 스킬

| 슬래시 | 기능 | 스크립트 |
|---|---|---|
| `/fetch_sample_h5` | 공식 데모 궤적 다운로드 → `data/` (멱등) | `scripts/fetch_sample_h5.py` |
| `/task_to_h5` | 모션 플래닝으로 행동 궤적 직접 생성 (**WSL 구동**) | `scripts/task_to_h5.py` |
| `/h5_add_images` | 궤적 리플레이 → 카메라 이미지 입힌 데이터셋 (+ 재현율 출력) | `scripts/h5_add_images.py` |
| `/h5_report` | 데이터셋 → 랜덤 에피소드 품질 리포트 (MD: 메타+필름스트립+mp4) | `scripts/h5_report.py` |
| `/view_task` | SAPIEN 뷰어 창 — 환경 둘러보기 | `scripts/view_task.py` |
| `/replay_h5` | SAPIEN 뷰어 창 — 저장된 에피소드 재생 | `scripts/replay_h5.py` |
| `/check_maniskill_env` | 환경 헬스체크 (import / CPU 시뮬 / CPU 렌더) | `scripts/check_maniskill_env.py` |

Python 함수 진입점:

| 모듈 | 함수 |
|---|---|
| `scripts.fetch_sample_h5` | `run(task, force=False)` |
| `scripts.task_to_h5` | `run(task, count, traj_name, obs_mode, sim_backend, only_success, ...)` |
| `scripts.h5_add_images` | `run(task, count, obs_mode, traj_path, num_envs, ...)` |
| `scripts.h5_report` | `run(traj_path, n=3, seed, fps, ...)` |
| `scripts.h5_to_media` *(라이브러리)* | `video(...)`, `preview(...)`, `card(...)` — h5_report가 사용 |
| `scripts.view_task` | `run(task, shader, blocking=False)` |
| `scripts.replay_h5` | `run(traj_path, episode, shader, blocking=False)` |
| `scripts.check_maniskill_env` | `run()` |

각 스크립트는 `if __name__ == "__main__":` 진입점에 동등한 argparse CLI가 있음.

## 디렉토리 구조

```
maniskill/
├── .claude/skills/     슬래시 커맨드 정의 (SKILL.md per 스킬)
├── scripts/            Python 스킬 모듈 (function + CLI 이중 인터페이스)
│   ├── custom_envs.py          커스텀 task 환경 (@register_env) — 예: ThreeColoredCubes-v1
│   ├── custom_solutions.py     커스텀 task의 모션플래닝 솔루션 (WSL)
│   ├── _wsl_solve_wrapper.py   빌트인 task용 WSL 래퍼 (Windows에서 직접 안 돎)
│   └── _wsl_solve_custom.py    커스텀 task용 WSL 시드 루프 생성기
├── notebooks/          스킬별 사용 노트북 (사용법 + 파라미터 예제)
├── data/               생성물 (gitignore, 재생성 가능)
│   └── datasets/<task>/
├── CLAUDE.md           이 파일
└── README.md           일반 소개
```

상태 분리 원칙 (자기 포함 / 재현 가능):

- **생성물 (출력)** — 행동 궤적·데이터셋·미디어는 출처(받아오기/직접 생성)와 무관하게 **전부 프로젝트 내부 `data/datasets/<task>/`**. `fetch_sample_h5` 조차 외부 캐시(`~/.maniskill/demos/`)에 받은 데모를 `data/`로 **복사해 들여온다** → 소비 단계는 외부 의존이 없다. (`task_to_h5`는 WSL에서 돌지만 `/mnt/c`를 통해 `data/`로 직접 출력.)
- **환경 (전제조건)** — Windows conda env와 WSL conda env는 둘 다 프로젝트 밖이지만, 문서 레시피로 재현 가능한 전제조건이라 자기 포함 원칙 위배가 아님 (코드/데이터가 아니라 실행 환경).
- `data/` 는 gitignore 대상 — 대용량이고 `git clone → 환경 준비 → fetch_sample_h5|task_to_h5 → h5_add_images` 로 재생성 가능하므로 git엔 *레시피*만 들어가고 데이터 자체는 안 들어감.

## 환경 가정

### Windows (소비 파이프라인 + task_to_h5 오케스트레이션)
- Windows 11 + NVIDIA GPU
- conda env: `maniskill`
- Python 실행 경로: `C:\Users\hun41\miniconda3\envs\maniskill\python.exe`
- 시뮬과 렌더 모두 **CPU 백엔드** (`sim_backend='cpu'`, `render_backend='cpu'`)
- 주요 패키지: `mani_skill 3.0.1`, `sapien 3.0.3`, `torch 2.12.0+cpu`, `jupyter`, `imageio[ffmpeg]`, `h5py`, `gymnasium`
- `pinocchio` 미설치 → EE 공간 컨트롤(`pd_ee_delta_pose`)과 텔레오퍼레이션 미지원.

### WSL (task_to_h5 행동 생성 전용)
- 배포판: `Ubuntu-22.04` (WSL2)
- Miniconda + `maniskill` env (Python 3.10): `torch 2.12.0+cpu`, `mani_skill 3.0.1`, `sapien 3.0.3`, `mplib 0.1.1`, `numpy<2`
- WSL Python 경로: `/root/miniconda3/envs/maniskill/bin/python`
- **소프트웨어 Vulkan**: `mesa-vulkan-drivers` (lavapipe). WSL엔 GPU Vulkan이 없어 sapien이 씬을 못 띄우므로 lavapipe ICD(`/usr/share/vulkan/icd.d/lvp_icd.x86_64.json`)로 우회.
- 이 값들은 `scripts/task_to_h5.py` 상단 상수(`WSL_DISTRO`, `WSL_PYTHON`, `WSL_VK_ICD`)에 박혀 있음.

`mplib`은 Linux 전용 바이너리(manylinux 휠)만 있어 Windows 네이티브에선 설치 불가 → 그래서 `task_to_h5`만 WSL에서 돈다.

## 데이터 흐름 (명령어)

```
# ① 행동 궤적 (택1)
/fetch_sample_h5 <task>              # Hugging Face → data/datasets/<task>/trajectory.h5
/task_to_h5 <task> <count>           # WSL 모션플래닝 → data/datasets/<task>/motionplanning.h5
        ↓ 액션 궤적 (pd_joint_pos, obs_mode=none, 이미지 없음)
# ② 데이터셋
/h5_add_images <task> <count>        # CPU 시뮬에서 리플레이하며 이미지 기록
   [--traj-path ...]                 #   fetch 궤적(trajectory.h5)을 입력으로 쓰려면 지정
        ↓ <source-stem>.<obs>.<ctrl>.<sim>.h5  (데이터셋)
# ③ 확인
/h5_report <hdf5> [n]                    # 랜덤 N개 에피소드 품질 리포트 (MD: 메타+필름스트립+mp4)
/view_task <task>                       # 환경 뷰어 창
/replay_h5 <hdf5> [episode]             # 에피소드 뷰어 재생
/check_maniskill_env                    # 환경 헬스체크
```

`h5_add_images`의 기본 입력은 `task_to_h5` 출력(`data/datasets/<task>/motionplanning.h5`). `fetch_sample_h5` 궤적(`trajectory.h5`)을 쓰려면 `--traj-path`(또는 함수 `traj_path=...`)로 명시.

## 출력 파일 명명 규칙

행동 궤적 (액션만, 이미지 없음):
```
data/datasets/<task>/trajectory.h5       (+ .json)   # fetch_sample_h5 (받아온 데모)
data/datasets/<task>/motionplanning.h5   (+ .json)   # task_to_h5 (직접 생성)
```

데이터셋 (이미지 포함) — 접두사는 **입력 궤적의 stem**을 따름 (출처 기록):
```
data/datasets/<task>/<source-stem>.<obs_mode>.<control_mode>.<sim_backend>.h5
```
예: `trajectory.h5` 입력 → `trajectory.rgb.pd_joint_pos.physx_cpu.h5`; `motionplanning.h5` 입력 → `motionplanning.rgb.pd_joint_pos.physx_cpu.h5`. 같은 옵션으로 재실행하면 덮어씀.

데이터셋의 `.json` 사이드카에는, 환경이 `label_metadata()` 를 노출하는 경우 그 **정수 라벨 → 문자열 사전**(예: `target_id → ["red","green","blue"]`)이 기록됨 — 데이터셋만으로 라벨 해독 가능.

내부 동작:
- `h5_add_images`: `replay_trajectory`가 입력 옆에 쓴 파일을 `data/datasets/<task>/` 로 이동 (입력이 이미 거기 있으면 no-op).
- `task_to_h5`: WSL 래퍼가 `<record-dir>/<task>/motionplanning/<name>.h5` 구조로 쓰는 걸, `task_to_h5.py`가 `data/datasets/<task>/<name>.h5` 로 평탄화 이동 후 빈 서브디렉토리 정리.

## task_to_h5가 지원하는 태스크

ManiSkill이 panda 모션플래닝 솔루션을 제공하는 빌트인 12개:
`PickCube-v1`, `StackCube-v1`, `PegInsertionSide-v1`, `PlugCharger-v1`, `PushCube-v1`, `PullCube-v1`, `PullCubeTool-v1`, `LiftPegUpright-v1`, `StackPyramid-v1`, `PlaceSphere-v1`, `DrawTriangle-v1`, `DrawSVG-v1`.

이 하네스의 커스텀 태스크: `ThreeColoredCubes-v1` (색 큐브 3개 중 시드로 정해진 하나를 집기 — 언어 지시형 VLA용).

멀티오브젝트/언어 지시형(PickClutterYCB 등)은 ManiSkill 솔루션 미제공 → 솔루션 스크립트 직접 작성 필요.

## 커스텀 task 추가하기

태스크별 지식은 **환경 클래스 하나(`scripts/custom_envs.py`)** 에만 둔다. 소비 스킬(`h5_add_images`/`h5_report`/`view_task`/`replay_h5`; `h5_to_media`는 h5_report의 렌더 라이브러리)은 태스크 이름을 모르고 약속만 따르므로, 새 task를 추가해도 **소비자 코드는 안 건드린다**.

1. `scripts/custom_envs.py` 에 `@register_env("<id>", ...)` 환경 클래스:
   - `_load_scene` / `_initialize_episode` / `evaluate` — 씬 구성, 시드 랜덤화, 성공 판정
   - `_get_obs_extra` — **매 스텝 기록할 신호** (반환 dict가 자동으로 데이터셋 `obs/extra` 에 실림)
   - `label_metadata()` *(선택)* — 정수 라벨 → 문자열 사전. `h5_add_images`가 데이터셋 `.json` 에 기록 (코드 없이 라벨 해독). 노출 안 하면 무시됨.
2. `scripts/custom_solutions.py` 에 모션플래닝 솔루션 함수 + `SOLUTIONS` 딕셔너리 등록.
3. `scripts/task_to_h5.py` 의 `CUSTOM_TASKS` 에 task id 추가.

## 코드 작성 시 유지해야 할 부분

- `scripts/h5_add_images.py`의 `gym.make` monkey-patch — `render_backend='cpu'` 기본값 주입. (`view_task.py`/`replay_h5.py`는 `gym.make` 호출에 `render_backend='cpu'`를 직접 명시.) Windows GPU 렌더 경로가 동작 불가능하므로 이 우회 필요.
- `scripts/_wsl_solve_wrapper.py`·`_wsl_solve_custom.py`의 우회 — ① `render_backend='cpu'` 주입 ② `RenderSystem` 실패 시 인자 없이 재호출(llvmpipe 자동 선택) ③ 호출자(`task_to_h5.py`)의 `VK_ICD_FILENAMES`=lavapipe. WSL headless 동작의 핵심.
- `scripts/h5_add_images.py`의 `if __name__ == "__main__":` 가드 — Windows multiprocessing은 `spawn` 방식이라 가드가 없으면 자식 프로세스가 무한 spawn 루프에 빠짐.
- `scripts/h5_to_media.py`의 trajectory 키 정렬은 **숫자순**(`int(k.split("_")[1])`) 필수 — 사전순(`sorted`)이면 에피소드 10개↑에서 `traj_10`이 `traj_2` 앞에 와 `--episode N` 인덱싱이 어긋남. `h5_report`·`card`·`video`가 모두 이 정렬에 의존.
- `scripts/h5_add_images.py`는 끝에 **재현율**(입력 success 대비 리플레이 success)을 출력 — WSL↔Windows 크로스-백엔드 발산 감지용 best-effort 경고(데이터는 안 지움).
- `scripts/h5_report.py`는 `scripts/h5_to_media.py`의 렌더러(`card`/`video`)를 재사용하는 소비 스킬. `h5_to_media`는 스킬이 아니라 **라이브러리** — 슬래시 커맨드 없음.
- `scripts/task_to_h5.py`의 subprocess는 `encoding='utf-8', errors='replace'` 필수 — WSL이 UTF-8(tqdm 유니코드)을 뱉는데 Windows 기본 cp949로 디코드하면 깨짐.
- `label_metadata` 훅의 제네릭성 — 소비자는 태스크 이름을 몰라야 한다. 메타데이터는 환경이 선언(`_get_obs_extra` / `label_metadata`)하고 소비자는 그 약속만 따른다. 태스크별 분기를 소비 스크립트에 넣지 말 것.
- 함수 인터페이스와 CLI 인터페이스의 동등성 — 새 옵션 추가 시 양쪽에 일관되게 반영.
