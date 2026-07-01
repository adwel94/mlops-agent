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
- 새 커스텀 task를 계약(카메라·tcp_pose·success·라벨)에 맞춰 자동 추가 (`add_custom_task`) — 소비 스킬은 안 건드림
- (선택) [GR00T-N1.7-3B](https://huggingface.co/nvidia/GR00T-N1.7-3B) 파인튜닝 분기:
  - EE 모션을 IK로 검증(`ee_verify`) → GR00T용 LeRobot v2.1(절대 EEF 10d)로 포장(`h5_to_lerobot`) → HF Hub 업로드 + 구조 검증(`hf_push_dataset`)
  - 클라우드(RunPod GPU, 과금): 파인튜닝(`gr00t_train`) → 정책 서버 서빙(`gr00t_serve`) → sim 닫힌 루프 평가(`gr00t_eval`) → 파드 확인/종료(`runpod_ls`/`runpod_down`)

## 동작 구조

```
① 행동 궤적(.h5) 만들기 — 택1
   fetch_sample_h5   공식 데모 다운로드 (빠름/베이스라인)   ┐
   task_to_h5        모션 플래닝으로 직접 생성 (WSL)         ┘ → data/datasets/<task>/*.h5
        ↓
② h5_add_images      리플레이하며 카메라 이미지 입힘 → 데이터셋 → h5_report / view_task / replay_h5
        ↓
④ GR00T용 EE 분기 (선택)   ee_verify (EE+IK 재현 게이트, WSL)
        → h5_to_lerobot (GR00T LeRobot v2.1, 절대 EEF 10d) → hf_push_dataset (HF Hub 업로드+검증)
        ↓
⑤ 클라우드 학습·서빙·평가 (RunPod GPU, 과금)
   gr00t_train (파인튜닝, 자가종료) → gr00t_serve (정책 서버 5555) → gr00t_eval (sim 닫힌 루프 → 성공률, WSL)
   runpod_ls / runpod_down (파드 확인 / 종료 = 과금 차단)
```

핵심: 행동을 어디서 얻었든(받아오든 직접 풀든) 결과가 같은 형식이라 ② 이후 단계는 전부 공유된다. 두 방법 모두 `data/datasets/<task>/` 에 떨구므로 외부 의존도 없다. ④는 GR00T 파인튜닝용 선택 분기 — ②의 데이터셋을 GR00T EEF 규약의 **절대 EEF(xyz+rot6d)** 로 변환한다(상대화는 GR00T가 내부 처리). ⑤는 변환·업로드한 데이터셋으로 실제 클라우드 GPU에서 파인튜닝하고, 학습된 정책을 sim에 붙여 닫힌 루프로 태스크 성공률을 재는 단계 — 실제 자원을 켜므로(과금) 명시 요청 시에만 돌리고 끝나면 종료한다.

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

Claude Code 안에서는 위 단계가 그대로 슬래시 커맨드: `/fetch_sample_h5`, `/task_to_h5`, `/h5_add_images`, `/h5_report`, `/view_task`, `/replay_h5`, `/check_maniskill_env`, `/ee_verify`, `/h5_to_lerobot`, `/hf_push_dataset`.

## 스킬과 호출 방식

각 스킬은 **슬래시 커맨드 / Python 함수 / CLI** 세 방식으로 동일하게 호출된다 (로컬 데이터 스킬은 추가로 `notebooks/<skill>.ipynb` 사용 예제 포함).

### 로컬 데이터 파이프라인 (10개 — Windows, 무과금)

| 스킬 | 슬래시 | Python 함수 | CLI |
|---|---|---|---|
| 데모 궤적 받기 | `/fetch_sample_h5` | `from scripts.fetch_sample_h5 import run` | `python scripts/fetch_sample_h5.py --task ...` |
| 행동 직접 생성 (WSL) | `/task_to_h5` | `from scripts.task_to_h5 import run` | `python scripts/task_to_h5.py --task ... --count ...` |
| 데이터셋 생성 | `/h5_add_images` | `from scripts.h5_add_images import run` | `python scripts/h5_add_images.py --task ... --count ...` |
| 품질 리포트 | `/h5_report` | `from scripts.h5_report import run` | `python scripts/h5_report.py --traj-path ... --n 3` |
| 환경 뷰어 | `/view_task` | `from scripts.view_task import run` | `python scripts/view_task.py --task ...` |
| 에피소드 재생 | `/replay_h5` | `from scripts.replay_h5 import run` | `python scripts/replay_h5.py --traj-path ... --episode ...` |
| 환경 헬스체크 | `/check_maniskill_env` | `from scripts.check_maniskill_env import run` | `python scripts/check_maniskill_env.py` |
| EE 재현 게이트 (WSL) | `/ee_verify` | `from scripts.ee_verify import run` | `python scripts/ee_verify.py --traj-path ... --count 10` |
| LeRobot 변환 | `/h5_to_lerobot` | `from scripts.h5_to_lerobot import run` | `python scripts/h5_to_lerobot.py --traj-path ... --instruction "..."` |
| HF Hub 업로드+검증 | `/hf_push_dataset` | `from scripts.hf_push_dataset import run` | `python scripts/hf_push_dataset.py <lerobot-dir> <repo_id>` |

`/add_custom_task <자연어 설명>` — 위 소비 스킬을 건드리지 않고 새 커스텀 task를 계약에 맞춰 추가하는 메타 스킬 (가능 판단 → `custom_envs.py`/`custom_solutions.py`/`task_to_h5.py` 구현 → `validate_custom_task.py` 검증). 자세한 계약은 `CLAUDE.md` "커스텀 task 추가하기" 참고.

### 클라우드 운영 (6개 — RunPod GPU 파드, ⚠️ 과금)

실제 GPU 자원을 켜는 작업이라 사용자가 명시 요청했을 때만 실행하고, 끝나면 반드시 `/runpod_down` 으로 종료한다.

| 스킬 | 슬래시 | 기능 |
|---|---|---|
| 파인튜닝 | `/gr00t_train` | HF 데이터셋으로 GR00T-N1.7-3B 학습 → 최종 모델만 HF 업로드 (자가종료) |
| 정책 서빙 | `/gr00t_serve` | 파인튜닝 모델을 정책 서버(5555/tcp)로 서빙 (평가용) |
| sim 평가 | `/gr00t_eval` | 정책을 sim에 붙여 닫힌 루프 롤아웃 → 태스크 성공률 (WSL 구동, 서버 필요) |
| 파드 생성 | `/runpod_up` | 범용 GPU 파드 생성 (gr00t_serve 의 하위 기반) |
| 파드 목록 | `/runpod_ls` | 떠 있는 파드 + 시간당 비용 합계 (읽기 전용) |
| 파드 종료 | `/runpod_down` | 파드 종료 (과금 차단) |

각 로컬 스킬에는 대응하는 `notebooks/<skill>.ipynb`가 있어 파라미터와 사용법을 보여준다 (클라우드 스킬은 떠 있는 파드가 전제라 노트북 없음 — `SKILL.md` 만). GR00T용 EE 분기의 배경(LeRobot 데이터셋 구조, 학습 한 row의 의미)은 `notebooks/gr00t_n17_training_explained.ipynb` 에서 추가로 설명한다.

## WSL 환경 준비 (`task_to_h5` · `ee_verify` · `gr00t_eval`)

이 세 스킬은 모션 플래닝/IK 솔버 `mplib`을 쓰는데, 이건 Linux 전용 바이너리만 있어 Windows 네이티브에선 설치가 안 된다. 그래서 이들만 WSL 안에서 돌리고 Windows 쪽이 구동한다. (나머지 스킬은 전부 Windows에서 동작.) `gr00t_eval`은 추가로 정책 서버와 통신하므로 WSL env에 일회성 `pip install pyzmq msgpack msgpack-numpy` 가 필요하다.

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
│   ├── ee_verify.py             EE-델타 IK 재현 게이트 (WSL 구동)
│   ├── h5_to_lerobot.py         데이터셋 → GR00T LeRobot v2.1 (절대 EEF 10d) 변환
│   ├── hf_push_dataset.py       LeRobot 디렉토리 → HF Hub 업로드 + 구조 검증
│   ├── gr00t_eval.py            정책 sim 닫힌 루프 평가 오케스트레이터 (WSL 구동)
│   ├── ee_convert.py            관절→EE 변환 수학 (델타+절대 EEF rot6d; 라이브러리, 스킬 아님)
│   ├── ik_exec.py               mplib IK 실행부 (ee_verify·gr00t_eval 공유; 라이브러리)
│   ├── _wsl_ee_verify.py        EE-델타 IK 재현 실행기 (ee_verify가 WSL에서 구동)
│   ├── _wsl_gr00t_eval.py       정책 롤아웃 클라이언트 (gr00t_eval이 WSL에서 구동)
│   ├── custom_envs.py            커스텀 task 환경 (ThreeColoredCubes-v1, ColoredCubeInBowl-v1)
│   ├── custom_solutions.py       커스텀 task 모션플래닝 솔루션 (WSL)
│   ├── validate_custom_task.py   커스텀 task 계약+EE 재현 검증
│   ├── _wsl_solve_wrapper.py     빌트인 task용 WSL 래퍼
│   └── _wsl_solve_custom.py      커스텀 task용 WSL 생성기
├── cloud/                 클라우드 운영 스킬 (RunPod GPU 파드, 과금)
│   ├── train/                GR00T 파인튜닝 컨트롤러 (launch_train.py)
│   ├── runpod/               파드 생성/서빙/목록/종료 (runpod_up·serve_up·runpod_ls·runpod_down)
│   └── reaper/               파드 종료를 RunPod 밖에서 보장하는 Cloudflare Worker (15분 크론 + Discord 버튼)
├── notebooks/             로컬 스킬별 사용 예제 (사용법 + 파라미터)
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

### GR00T용 LeRobot 출력 (④, `h5_to_lerobot`)

EE 분기(④)는 데이터셋을 GR00T-flavored **LeRobot v2.1** 디렉토리로 변환한다:

```
data/datasets/<task>/lerobot/
├── meta/{info.json, episodes.jsonl, tasks.jsonl, modality.json, stats.json}
├── data/chunk-000/episode_<i:06d>.parquet      # observation.state, action(10d 절대 EEF), 인덱스
└── videos/chunk-000/observation.images.<cam>/episode_<i:06d>.mp4
```

- **액션 = 10d 절대 EEF** `[eef_x,y,z, rot6d_0..5, gripper]` (`ActionFormat.XYZ_ROT6D`), **상태 = `[qpos(Q), eef_abs(9)]`**. `action[t]`=다음 스텝 절대 pose, `state[t]`=현재 pose → GR00T가 `rep=RELATIVE`+`state_key="eef"` 로 상대화한다(우리는 절대값을 저장). rot6d는 회전행렬 첫 두 행(GR00T `pose.py` 컨벤션).
- 프레임 수 N = T−1 (parquet 행수 == mp4 프레임수). 지시문은 `label_metadata` 에서 생성(`--instruction "pick up the {target_id} cube"`). 멀티 카메라면 `videos/.../observation.images.<cam>/` 가 카메라 수만큼.
- meta 스키마는 Isaac-GR00T 공식 예제(`demo_data/cube_to_bowl_5`)와 정합 확인됨. 학습 전 GR00T env에서 `scripts/repair_lerobot_metadata.py <out> --embodiment-tag <tag>` 로 `stats.json`/`relative_stats.json` 재생성 권장(로더가 `stats.json` 존재를 요구; `relative_stats` 는 EEF 상대 액션 정규화용·선택).

### 다중 카메라 / 손목 카메라 (멀티캠)

파이프라인은 카메라 개수를 **데이터에서 발견**한다 — 어디에도 카메라 이름·개수를 하드코딩하지 않으므로 1캠/멀티캠을 같은 코드로 처리하고, 기존 1캠 데이터셋·모델은 그대로 동작한다(하위호환).

**손목 카메라 데이터셋 만들기** — `h5_add_images` 에 `--robot-uids panda_wristcam` 만 주면 된다. ManiSkill 내장 `PandaWristCam` 로봇이 그리퍼(`camera_link`)에 `hand_camera` 를 자동으로 단다. 팔 운동학은 panda 와 동일하므로 기존 액션 궤적(`motionplanning.h5`)을 그대로 리플레이하며 손목 이미지만 추가로 기록한다(WSL 재생성 불필요). 쓴 로봇은 출력 사이드카(`env_info.robot_uids`)에 기록돼 하류(`h5_to_lerobot`/`gr00t_eval`/`ee_verify`)가 같은 카메라 세트로 env 를 구성한다.

```cmd
:: 손목캠 데이터셋 생성 (base_camera + hand_camera 2캠) — 별도 stem 으로 1캠 데이터셋 보존
copy data\datasets\ThreeColoredCubes-v1\motionplanning.h5 data\datasets\ThreeColoredCubes-v1\motionplanning_wristcam.h5
copy data\datasets\ThreeColoredCubes-v1\motionplanning.json data\datasets\ThreeColoredCubes-v1\motionplanning_wristcam.json
python scripts\h5_add_images.py --task ThreeColoredCubes-v1 --traj-path data\datasets\ThreeColoredCubes-v1\motionplanning_wristcam.h5 --count 1000 --robot-uids panda_wristcam

:: LeRobot 변환 — 데이터의 모든 카메라를 자동 포장 (각 카메라가 observation.images.<cam>/ 로)
::   특정 카메라만 쓰려면 --camera base_camera 또는 --cameras base_camera,hand_camera
python scripts\h5_to_lerobot.py --traj-path data\datasets\ThreeColoredCubes-v1\motionplanning_wristcam.rgb.pd_joint_pos.physx_cpu.h5 --instruction "pick up the {target_id} cube"
```

- `h5_to_lerobot` 는 발견한 카메라마다 `videos/.../observation.images.<cam>/` 와 `modality.json` video 키를 만든다(기본 = 전체; `--camera`/`--cameras` 로 override). `info.json` 의 `total_videos = 에피소드 × 카메라 수`.
- 학습(`new_embodiment_config.py`)·평가(`_wsl_gr00t_eval.py`)는 데이터셋 `meta/modality.json` 의 video 키에서 카메라 세트를 읽어 그대로 따른다 — 학습 이미지나 평가 코드를 캠 수에 맞춰 고칠 필요 없다.
- **체크포인트는 카메라 수가 고정**(비전 인코더+projector가 그 입력으로 굳음) — 1캠 모델은 2캠 입력을 못 먹고 반대도 안 됨. 그래서 캠 구성이 다르면 **HF 태그로 분리**한다(예: 데이터셋 `v1`=1캠, `v2`=손목캠 2캠). 손목캠 도입의 설계·검증·성공률 비교는 `notes/wrist-camera-scope.md`.

## 출력 파일 명명 규칙

```
data/datasets/<task>/trajectory.h5                             # fetch_sample_h5 (받아온 데모)
data/datasets/<task>/motionplanning.h5                         # task_to_h5 (직접 생성)
data/datasets/<task>/<source-stem>.<obs>.<control>.<sim>.h5    # h5_add_images (이미지 포함)
```

데이터셋 출력의 접두사는 입력 궤적 stem을 따른다 — 받아온 데모 입력이면 `trajectory.rgb...`, 직접 생성 입력이면 `motionplanning.rgb...`. 출처가 파일명에 남는 셈. 같은 옵션으로 재실행하면 덮어씀.

## 지원 태스크

**빌트인 12개** — `task_to_h5`가 행동을 생성할 수 있는, ManiSkill이 panda 모션플래닝 솔루션을 제공하는 태스크:
`PickCube-v1`, `StackCube-v1`, `PegInsertionSide-v1`, `PlugCharger-v1`, `PushCube-v1`, `PullCube-v1`, `PullCubeTool-v1`, `LiftPegUpright-v1`, `StackPyramid-v1`, `PlaceSphere-v1`, `DrawTriangle-v1`, `DrawSVG-v1`.

**이 하네스의 커스텀 태스크 2개** (`scripts/custom_envs.py` 에 정의, 둘 다 언어 지시형 VLA용 — 빨강/초록/파랑 큐브 3개 중 **시드로 정해진 한 색**을 목표로 한다):

| task id | 목표 | 성공 판정 (`evaluate()`) | 지시문 예 |
|---|---|---|---|
| `ThreeColoredCubes-v1` | 시드가 고른 색 큐브를 **집어 들어올린다** | 타겟 큐브가 잡힌 채 테이블에서 들림 | `pick up the {target_id} cube` |
| `ColoredCubeInBowl-v1` | 시드가 고른 색 큐브를 집어 **그릇에 담는다** | 타겟 큐브가 그릇 안에서 놓이고(릴리스) 정지 | `put the {target_id} cube in the bowl` |

두 태스크 모두 소비 스킬이 따르는 계약을 그대로 지킨다 — 주 카메라 `base_camera`(PickCubeEnv 상속), `_get_obs_extra` 의 `tcp_pose`, `evaluate() → {"success": ...}`, 그리고 색 디코더 `label_metadata()`(`target_id → ["red","green","blue"]`). 그릇은 메시 에셋 없이 박스 벽으로 만든 얕은 트레이라 자기 포함적이다(다운로드/메시-충돌 IK 변수 없음). 같은 계약 덕에 새 task를 추가해도 `h5_add_images`/`h5_report`/`ee_verify`/`h5_to_lerobot` 등 소비 스킬은 **코드 수정 없이** 재사용된다 — `ColoredCubeInBowl-v1`이 이를 실증한 두 번째 사례.

새 커스텀 task를 추가하는 법은 `/add_custom_task` 스킬 또는 `CLAUDE.md` "커스텀 task 추가하기"(계약 + `validate_custom_task.py` 검증) 참고.

## 알려진 제약

- 시뮬과 렌더 모두 CPU 백엔드 — 작은 배치엔 충분하지만 대규모 병렬 생성은 외부 인프라가 필요.
- `task_to_h5`는 WSL + 소프트웨어 Vulkan(lavapipe) 위에서 돌아 GPU 가속이 없음 — 단일 태스크 데이터엔 충분하지만 대량 생성은 느림.
- 멀티오브젝트/언어 지시형 빌트인 태스크(PickClutterYCB 등)는 모션플래닝 솔루션 미제공 → 솔루션 직접 작성 필요.
- 텔레오퍼레이션(직접 조작)과 라이브 EE 공간 컨트롤 모드는 미지원 — `pinocchio` 의존성 필요한데 현재 환경에 미설치. (GR00T용 EE 데이터셋은 `pinocchio` 없이 오프라인 변환 + WSL mplib IK로 생성 — `ee_verify`/`h5_to_lerobot`.)
- 학습·서빙·평가(⑤)는 **외부 GPU(RunPod) 위에서** 돈다 — 로컬 GPU로는 GR00T-3B 파인튜닝이 불가하므로 클라우드 스킬(`gr00t_train`/`gr00t_serve`/`gr00t_eval`)로 분리. 실제 자원을 켜는 과금 작업이라 명시 요청 시에만 실행하고 끝나면 `/runpod_down`. `h5_to_lerobot` 출력은 GR00T-flavored LeRobot v2.1 스펙(Isaac-GR00T 공식 예제 `cube_to_bowl_5`와 meta 정합, 액션=절대 EEF xyz+rot6d)을 직접 작성한 것 — 학습 전 GR00T env에서 `scripts/repair_lerobot_metadata.py <out> --embodiment-tag <tag>` 로 `stats.json`/`relative_stats.json`(EEF 상대 액션 정규화)을 재생성하는 것을 권장.
- **RunPod community 호스트가 간헐적으로 `CUDA unknown error`(GPU 붙어 있는데 torch가 못 잡음, devices=0)로 serve/train 기동에 실패**한다. `serve_policy.sh` 에 재시도 루프(fresh process)가 있어 *일시적* 결함은 자동 회복하지만, **호스트 GPU 영구 결함**이면 재시도로 안 풀린다 — 게다가 community 스케줄러가 같은 불량 호스트(같은 publicIp)를 반복 배정할 수 있다. 이때는 파드를 종료하고 **`--cloud-type SECURE`** (다른 호스트 풀)로 다시 띄운다. 파드 생성 직후 `publicIp` 가 직전 불량 호스트와 같으면 부팅 완료를 기다리지 말고 즉시 종료해 과금을 아낀다.
