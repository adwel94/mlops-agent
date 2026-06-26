# ManiSkill 하네스

[ManiSkill3](https://www.maniskill.ai) 위에 얹은 Windows용 VLA 데이터셋 생성 하네스. **task 환경**에서 로봇 팔의 **행동 궤적(.h5)** 을 만들고, 거기에 카메라 이미지를 입혀 **(이미지 + 액션) 데이터셋(.h5)** 을 만든 뒤, 품질 리포트·뷰어로 확인하는 도구 모음.

핵심 개념 두 개: **환경 = task**, **행동 = .h5**.

열 가지 스킬을 **슬래시 커맨드 / Python 함수 / CLI / 노트북** 네 인터페이스에서 동일하게 호출할 수 있게 설계됨.

## 협업 규칙 (AI 작업 지침 — 다른 모든 지침과 함께 우선 적용)

**기본 자세** — 목표는 "다음 단계를 굴리는 것"이 아니라 "올바른 것을 만드는 것"이다. 막히면 어떻게든 통과하지 말고, 무엇이 왜 막혔는지부터 드러내라. 성공 판정은 "동작했다"가 아니라 **"약속한 산출물이 무결하게 나왔다"**.

### 핵심 게이트 — 장애물을 만나면 우회하기 전에 먼저 분류한다
에러·누락·이상을 만나면, 손대기 전에 반드시 한 번 분류한다:

- **환경 quirk** — 만들려는 산출물과 무관한 실행환경의 마찰 (인코딩, User-Agent, 경로, 권한 토글, 누락된 시스템 패키지 등). → 인라인으로 고치고 진행 가능. 단 무엇을 고쳤는지 한 줄 남긴다.
- **결함(defect)** — 만들고 있는 것 / 약속한 산출물이 잘못됐다는 신호 (기대한 파일이 없음·형태가 다름, 출력이 스펙 불일치, 단계 결과물이 불완전). → **멈춘다. 우회 금지.** 결함을 헤드라인으로 보고하고 결정을 받는다.

확신이 안 서면 **결함으로 취급**한다(안전한 쪽).

### 산출물 무결성 체크
"이걸 로드/실행할 수 있나?"가 아니라 **"이 단계가 내놓기로 한 것을 온전히 내놨나?"**를 검증한다. 다음 단계의 입력으로 쓰기 전에 기대 형태와 일치하는지 확인한다. 불일치 = 결함 = 멈춤.

### 결함 보고 순서
1. 결함을 **첫 문장으로** 명시한다. ("X 단계가 불완전한 Y를 산출함 — 버그다")
2. 근본 원인은 **아는 만큼만** 말하고, 모르면 모른다고 한다. 추측을 사실로 포장 금지.
3. 우회로가 있어도 **"이건 우회다"라고 라벨**을 붙여 *옵션으로만* 제시한다. 기본 추천은 항상 "결함을 고친다".
4. 사용자가 고르기 전엔 우회로 진행하지 않는다.

### 멈춤·경계 규칙
- **시도 예산** — 한 접근이 **2번** 실패하면 멈추고 보고 후 질문. 다른 우회를 연쇄 시도하지 않는다.
- **외부 상태는 캐지 말고 요청** — 내 실행환경 **밖**(클라우드 콘솔 로그, W&B/Prefect 대시보드, 사용자만 보는 화면, 시크릿, 파드 내부)은 스스로 긁지 말고 **사용자에게 요청**한다. (예: 학습 실패 로그는 GraphQL 삽질 대신 "콘솔 로그 붙여주세요".)
- **조용한 우회/변경 금지** — 패키지 설치, 도구 대체, 스펙·인터페이스 변경, 임시 mock/더미 작성은 **먼저 승인**. 작동 중인 conda/venv 환경은 안 건드린다.
- **과금·비가역 작업은 확인 먼저** — RunPod 파드 생성, 이미지 push, 리포 삭제/덮어쓰기 등은 실행 전 한 줄 확인. (빌드처럼 무과금·가역 작업은 진행 가능.)
- **역할 분담** — AI: 코드·빌드·로컬 분석. 사용자: 시크릿·콘솔 로그·승인. 모니터링은 파드가 push(Discord/W&B)하고 AI는 *가끔* 조회(턴 기반 — 백그라운드 데몬 아님).
- **장시간 클라우드 작업 폴링 패턴** — 파드 부팅·학습·serve 같은 **하네스가 추적 못 하는 외부 상태**(내가 시작한 로컬 작업이 아니라 RunPod이 도는 것)는 자동 알림이 안 오므로 **직접 폴링**한다. 방식: `Bash`를 `run_in_background`로 띄워 **`sleep <N초> && <확인 명령>`**(확인 = `read_logs.py`/`runpod_ls.py` 등)을 걸면, sleep+확인이 끝날 때 task-notification 이 와서 출력을 읽고 다음 수를 정한다. **각 폴링은 일회성**(sleep 1번 → 확인 1번 → 알림 → 판정)이라 턴 기반이며 지속 데몬이 아니다(루프로 계속 돌리면 선을 넘음). 간격 가이드: 부팅/접속대기 ~수분(5~8분), 학습 진행 ~10~15분, stall 의심 시 더 촘촘히. 포그라운드 `sleep`은 하네스가 막으므로 반드시 백그라운드로.

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
        ↓
④ GR00T용 EE 분기 (선택) — 관절 데이터셋을 GR00T용 LeRobot v2.1(절대 EEF)로 포장
   ee_verify         EE 모션을 7d 델타로 만들어 mplib IK로 sim 성공 재현 확인 (게이트, WSL)
   h5_to_lerobot     절대 EEF 액션(10d: xyz+rot6d+gripper) + mp4 + parquet/meta 로 LeRobot v2.1 변환
   hf_push_dataset   LeRobot 데이터셋을 HF Hub 로 업로드 + 구조 검증 (학습 파드의 단일 출처)
        ↓
⑤ 클라우드 학습·서빙 (RunPod GPU 파드 — 과금)
   gr00t_train       HF 데이터셋으로 GR00T-N1.7-3B 파인튜닝 → 최종 모델만 HF 업로드 (자가종료)
   gr00t_serve       파인튜닝 모델을 정책 서버(5555/tcp)로 서빙 → WSL 평가 롤아웃이 붙음
   gr00t_eval        정책을 sim에 붙여 닫힌 루프 롤아웃 → 태스크 성공률 (WSL, 무과금; 서버는 과금)
   runpod_ls/down    떠 있는 파드 확인 / 종료 (과금 차단)
```

행동 궤적을 얻는 방법은 둘(받아오기 / 직접 생성)이지만, 둘 다 `data/datasets/<task>/` 에 같은 자기기술(self-describing) 형식으로 떨군다. 그래서 ② 이후 단계는 **출처를 몰라도 동일하게** 동작한다 (`.json` 사이드카에서 env_id·control_mode를 읽음).

④는 [GR00T-N1.7-3B](https://huggingface.co/nvidia/GR00T-N1.7-3B) 파인튜닝용 선택 분기다. GR00T EEF 규약에 맞춰 기록된 관절 궤적을 **절대 EEF(xyz+rot6d)** 로 변환(`scripts/ee_convert.py`)해 액션으로 저장하고, **상대화는 GR00T가 내부에서** 처리한다(`rep=RELATIVE` + `state_key`). 먼저 ee_verify로 "EE 모션이 IK로 재현되는가"를 게이트한 뒤 h5_to_lerobot로 포장하는 순서. (ee_verify는 검증 수단으로 7d 델타 표현을 쓰지만, 저장 포맷은 절대 EEF — 같은 궤적의 두 표현.)

## 열 가지 스킬

| 슬래시 | 기능 | 스크립트 |
|---|---|---|
| `/fetch_sample_h5` | 공식 데모 궤적 다운로드 → `data/` (멱등) | `scripts/fetch_sample_h5.py` |
| `/task_to_h5` | 모션 플래닝으로 행동 궤적 직접 생성 (**WSL 구동**) | `scripts/task_to_h5.py` |
| `/h5_add_images` | 궤적 리플레이 → 카메라 이미지 입힌 데이터셋 (+ 재현율 출력) | `scripts/h5_add_images.py` |
| `/h5_report` | 데이터셋 → 랜덤 에피소드 품질 리포트 (MD: 메타+필름스트립+mp4) | `scripts/h5_report.py` |
| `/view_task` | SAPIEN 뷰어 창 — 환경 둘러보기 | `scripts/view_task.py` |
| `/replay_h5` | SAPIEN 뷰어 창 — 저장된 에피소드 재생 | `scripts/replay_h5.py` |
| `/check_maniskill_env` | 환경 헬스체크 (import / CPU 시뮬 / CPU 렌더) | `scripts/check_maniskill_env.py` |
| `/ee_verify` | EE-델타를 mplib IK로 풀어 sim 성공 재현 확인 (**WSL 구동**) | `scripts/ee_verify.py` |
| `/h5_to_lerobot` | 데이터셋 → GR00T LeRobot v2.1(절대 EEF 10d) 변환 (오프라인) | `scripts/h5_to_lerobot.py` |
| `/hf_push_dataset` | LeRobot 데이터셋 → HF Hub 업로드 + 구조 검증 (오프라인) | `scripts/hf_push_dataset.py` |

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
| `scripts.ee_verify` | `run(traj_path, task=None, count=10, seed=0, sim_backend, ...)` |
| `scripts.h5_to_lerobot` | `run(traj_path, out=None, fps=20, instruction=None, camera=None)` |
| `scripts.hf_push_dataset` | `run(local_dir, repo_id, private=False, verify_only=False, version=None, task=None)` · `verify(repo_id)` |
| `scripts.ee_convert` *(라이브러리)* | `episode_joint_to_ee(...)`, `ee_delta_to_target_pose(...)` — ee_verify·h5_to_lerobot가 사용 |
| `scripts.manifest` *(라이브러리)* | `add_dataset(...)`, `add_model(...)`, `set_eval(...)`, `slug_from_repo(...)` — HF 버전 원장(MANIFEST.yaml) |

각 스크립트는 `if __name__ == "__main__":` 진입점에 동등한 argparse CLI가 있음.

## 클라우드 운영 스킬 (⑤ — RunPod GPU 파드, 과금)

위 "열 가지 스킬"이 로컬/오프라인 데이터 파이프라인이라면, 아래는 **클라우드 GPU 파드**를 켜고 끄는 운영 스킬이다. 전부 `cloud/` 아래에 있고, 실제 자원을 켜는(=과금) 작업이라 사용자가 명시 요청했을 때만 실행하며 끝나면 반드시 종료한다.

| 슬래시 | 기능 | 스크립트 |
|---|---|---|
| `/gr00t_train` | HF 데이터셋으로 GR00T-N1.7-3B 파인튜닝 → 최종 모델만 HF 업로드 (자가종료) | `cloud/train/launch_train.py` |
| `/gr00t_serve` | 파인튜닝 모델을 정책 서버(5555/tcp)로 서빙 (④ 평가용) | `cloud/runpod/serve_up.py` |
| `/gr00t_eval` | 정책을 sim에 붙여 닫힌 루프 롤아웃 → 태스크 성공률 (WSL 구동, 서버 필요) | `scripts/gr00t_eval.py` |
| `/runpod_up` | 범용 GPU 파드 생성 (gr00t_serve 의 하위 기반; idle/serve/smoke 모드) | `cloud/runpod/runpod_up.py` |
| `/runpod_ls` | 떠 있는 파드 목록 + 시간당 비용 합계 (읽기 전용) | `cloud/runpod/runpod_ls.py` |
| `/runpod_down` | 파드 종료 (과금 차단) | `cloud/runpod/runpod_down.py` |

| 모듈 | 함수 |
|---|---|
| `cloud.train.launch_train` | `run(name, gpu, hf_dataset_repo, hf_output_repo, max_steps, ..., full=False)` |
| `cloud.runpod.serve_up` | `run(hf_model, name, gpu, hf_model_subdir=None, ...)` — runpod_up.run(mode="serve") 래퍼 |
| `cloud.runpod.runpod_up` | `run(name, gpu, ..., mode="idle", hf_dataset=None, hf_model=None, ...)` |
| `scripts.gr00t_eval` | `run(traj_path, server_host, server_port=5555, task=None, count=10, seed=0, instruction=None, action_steps=16, ...)` — WSL 롤아웃 (`ik_exec` 를 ee_verify 와 공유) |

서빙은 `runpod_up` 의 한 *모드*(MODE=serve)일 뿐 — `gr00t_serve` 는 거기에 서빙 기본값(A5000 24GB, hf_model 필수, 5555 포트)을 박은 얇은 래퍼. 학습은 전용 이미지(`maniskill-gr00t-train`)·전용 컨트롤러(`launch_train.py`)로 분리돼 있고, 파드가 부팅 때 Prefect flow(prepare→repair→train→upload→request_termination)를 자급 실행한다. **종료는 파드가 자기를 RunPod API로 못 죽이므로(파드→RunPod 호출은 데이터센터 공유 egress IP가 RunPod WAF/레이트리밋에 걸려 랜덤 403) 외부 Cloudflare Worker(`cloud/reaper`)에 위임**한다 — 파드는 3초마다 Worker에 종료요청을 보내고(살아있음=아직 안 죽음, 죽을 때까지 반복; 2번째부터 RunPod 채널로도 직접 알림), 실제 DELETE는 RunPod 밖에서 100% 도는 Worker가 수행한다. Worker는 추가로 15분 크론으로 1h 초과한 orphan 파드를 Discord 버튼 알림으로 잡는다(하드 크래시로 핑조차 못 보낸 파드 대비). `WORKER_TERMINATE_URL` 미설정 시 파드는 옛 직접삭제로 폴백(`_direct_delete_fallback`). 평가(④ 롤아웃)는 `/gr00t_eval` 스킬 — 성공 기준은 태스크 환경의 `evaluate().success`(시뮬에서 과제를 실제로 해냈나) 그대로다. IK 실행부(`ik_exec.py`)를 `ee_verify` 와 공유하므로, 조용히 거짓말할 위험이 큰 경로(env 구성/프레임 변환/mplib IK/sim 스텝)는 ee_verify 게이트로 이미 검증된다. 출력의 `orig_success`(기록 에피소드 성공률, ~100% 기대)가 매 실행 자가 기준점.

## 디렉토리 구조

```
maniskill/
├── .claude/skills/     슬래시 커맨드 정의 (SKILL.md per 스킬)
├── scripts/            Python 스킬 모듈 (function + CLI 이중 인터페이스)
│   ├── custom_envs.py          커스텀 task 환경 (@register_env) — 예: ThreeColoredCubes-v1
│   ├── custom_solutions.py     커스텀 task의 모션플래닝 솔루션 (WSL)
│   ├── _wsl_solve_wrapper.py   빌트인 task용 WSL 래퍼 (Windows에서 직접 안 돎)
│   ├── _wsl_solve_custom.py    커스텀 task용 WSL 시드 루프 생성기
│   ├── ee_convert.py           관절→EE 변환 수학 (델타+절대 EEF rot6d; 라이브러리, 스킬 아님)
│   ├── manifest.py             HF 버전 원장 읽기/쓰기 (MANIFEST.yaml; 라이브러리 + show/set-eval CLI)
│   └── _wsl_ee_verify.py       EE-델타 IK 재현 실행기 (ee_verify가 WSL에서 구동)
├── notebooks/          스킬별 사용 노트북 (사용법 + 파라미터 예제)
├── data/               생성물 (gitignore, 재생성 가능)
│   └── datasets/<task>/
├── MANIFEST.yaml       데이터셋·모델 HF 버전 원장 (커밋됨 — 버전 번호의 단일 출처)
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
- `pinocchio` 미설치 → 라이브 EE 공간 컨트롤(`pd_ee_delta_pose`)과 텔레오퍼레이션 미지원. (GR00T용 EE 데이터셋(④)은 pinocchio 없이 오프라인 변환 + WSL mplib IK로 만든다.)

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
# ④ GR00T용 EE 분기 (선택) — 입력은 ②의 데이터셋 h5
/ee_verify <hdf5> [count]               # WSL: 랜덤 N개 EE-델타 IK 재현 게이트 (기본 10; 0=전체)
        ↓ reproduction_rate≈1.0 이면 방식 건강
/h5_to_lerobot <hdf5> [--instruction "..."]   # GR00T LeRobot v2.1 변환 (절대 EEF 10d + mp4 + parquet/meta)
        ↓ <hdf5 디렉토리>/lerobot/
/hf_push_dataset <lerobot-dir> <repo_id>      # HF Hub 업로드 + 구조 검증 (학습 파드가 받을 단일 출처)
   [--version v1]                             #   불변 버전 태그 박고 MANIFEST.yaml 에 기록 (중복이면 에러)
   [--verify-only]                            #   업로드 없이 기존 repo 점검만
        ↓ huggingface.co/datasets/<repo_id>@<version>  → GR00T 학습 (클라우드)
# 학습은 데이터셋을 repo@version 으로 받고 모델 태그를 <version>-s<steps> 로 자동 도출:
/gr00t_train --hf-dataset-repo <repo_id>@v1 --hf-output-repo <model_repo> --max-steps 30000
        ↓ huggingface.co/<model_repo>@v1-s30000  (+ MANIFEST.yaml 에 eval=null 로 기록)
```

`h5_add_images`의 기본 입력은 `task_to_h5` 출력(`data/datasets/<task>/motionplanning.h5`). `fetch_sample_h5` 궤적(`trajectory.h5`)을 쓰려면 `--traj-path`(또는 함수 `traj_path=...`)로 명시.

④의 입력은 ②가 만든 **이미지 데이터셋 h5** (rgb + `obs/extra/tcp_pose` + 관절 액션 필요). `ee_verify`는 검증만(파일 안 만듦), `h5_to_lerobot`은 입력 옆 `lerobot/` 에 변환 결과를 떨군다. 둘 다 task-무관 — `tcp_pose`·`label_metadata` 약속만 따른다.

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

### HF 명명·버전 컨벤션 (반복 업로드가 안 꼬이게)

재학습·데이터 재생성을 반복하면 repo 이름이 증식하거나(`-ft2`, `-final`) 덮어쓰기로 이전 게 사라진다. 둘 다 막는 규칙: **태스크당 repo 하나 + git 태그로 버전**. HF 는 git 이라 한 repo 에 여러 스냅샷(태그)을 공짜로 쌓는다.

```
데이터셋  adwel94/maniskill-<slug>-lerobot        # 태스크당 하나
              └─ tag v1 (1000ep), v2 (3000ep) ...   # 에피소드/생성방식 바뀌면 새 태그(불변)
모델      adwel94/gr00t-<slug>                      # 태스크당 하나
              ├─ main                                 # 최신 업로드(자동); "best"는 직접 태그로 골라 씀
              └─ tag <ds_ver>-s<steps>[-full]         # 예: v1-s3000, v2-s30000-full
```

- **로컬은 작업 사본, HF 태그가 버전 진실.** `data/` 는 gitignore + 재생성 가능 → 로컬엔 *최신 빌드 하나*만. 과거 버전은 HF 태그에서 pull. 모델은 애초에 로컬에 없음(파드→HF 직행).
- **버전 번호의 단일 출처 = `MANIFEST.yaml`** (repo 루트, 커밋됨). "어떤 버전이 어디 있고 eval 이 얼마"를 잇는 작은 텍스트 지도. 큰 데이터는 HF, 로컬엔 최신본, 매핑은 여기 — 세 역할이 안 겹친다.
- **태그는 불변.** `hf_push_dataset --version v1` 은 같은 태그가 이미 있으면 **에러**(데이터가 바뀌었으면 새 번호를 쓰라는 신호 — 덮어쓰지 않음). 모델 태그 충돌은 파드에서 경고만(학습 성공을 태그 때문에 죽이지 않음; main 은 갱신됨).
- **자동 기록**: `hf_push_dataset --version` → `add_dataset`(업로드+태그 성공 직후). `launch_train` → `add_model`(런치 시 `eval=null`). 모델 eval 은 평가 후 수동: `python scripts/manifest.py set-eval <slug> <model> <값>`.
- **slug** = dataset repo 이름에서 추출(`maniskill-<slug>-lerobot` → `<slug>`). push/train 양쪽이 같은 dataset repo 를 알아 MANIFEST 태스크 키가 일치한다.

GR00T용 LeRobot 출력 (④, 디렉토리):
```
data/datasets/<task>/lerobot/
├── meta/{info.json, episodes.jsonl, tasks.jsonl, modality.json, stats.json}
├── data/chunk-000/episode_<i:06d>.parquet      # observation.state, action(10d 절대 EEF), 인덱스
└── videos/chunk-000/observation.images.<cam>/episode_<i:06d>.mp4
```
액션 = **10d 절대 EEF** `[eef_x,y,z, rot6d_0..5, gripper]` (`ActionFormat.XYZ_ROT6D`), 상태 = **`[qpos(Q), eef_abs(9)]`**. `action[t]`=다음 스텝 절대 pose, `state[t]`=현재 pose → GR00T가 `rep=RELATIVE`+`state_key="eef"` 로 상대화. rot6d는 회전행렬 첫 두 행(GR00T `pose.py` 컨벤션, round-trip 오차 ~3e-7). 프레임 수 N = T-1 (parquet 행수 == mp4 프레임수). 지시문은 `label_metadata` 에서 생성(`--instruction "pick up the {target_id} cube"`). `codebase_version v2.1` 타깃 — meta 스키마는 Isaac-GR00T 공식 예제(`demo_data/cube_to_bowl_5`)와 정합 확인됨(info.json `info` 블록·modality `annotation.original_key="task_index"`·stats `q01/q99`). 학습 전 GR00T env에서 `scripts/repair_lerobot_metadata.py <out> --embodiment-tag <tag>` 로 `stats.json`/`relative_stats.json` 재생성 권장(로더가 stats.json 존재를 요구; relative_stats는 EEF 상대 액션 정규화용·선택).

내부 동작:
- `h5_add_images`: `replay_trajectory`가 입력 옆에 쓴 파일을 `data/datasets/<task>/` 로 이동 (입력이 이미 거기 있으면 no-op).
- `task_to_h5`: WSL 래퍼가 `<record-dir>/<task>/motionplanning/<name>.h5` 구조로 쓰는 걸, `task_to_h5.py`가 `data/datasets/<task>/<name>.h5` 로 평탄화 이동 후 빈 서브디렉토리 정리.

## task_to_h5가 지원하는 태스크

ManiSkill이 panda 모션플래닝 솔루션을 제공하는 빌트인 12개:
`PickCube-v1`, `StackCube-v1`, `PegInsertionSide-v1`, `PlugCharger-v1`, `PushCube-v1`, `PullCube-v1`, `PullCubeTool-v1`, `LiftPegUpright-v1`, `StackPyramid-v1`, `PlaceSphere-v1`, `DrawTriangle-v1`, `DrawSVG-v1`.

이 하네스의 커스텀 태스크 (둘 다 언어 지시형 VLA용 — 빨강/초록/파랑 큐브 3개 중 시드로 정해진 한 색이 목표):
- `ThreeColoredCubes-v1` — 시드가 고른 색 큐브를 집어 들어올림 (성공 = 잡힌 채 테이블에서 들림).
- `ColoredCubeInBowl-v1` — 시드가 고른 색 큐브를 집어 그릇에 담음 (성공 = 그릇 안에서 놓이고 정지). 그릇은 박스 벽 트레이(에셋 없음).

멀티오브젝트/언어 지시형(PickClutterYCB 등)은 ManiSkill 솔루션 미제공 → 솔루션 스크립트 직접 작성 필요.

## 커스텀 task 추가하기

태스크별 지식은 **환경 클래스 하나(`scripts/custom_envs.py`)** 에만 둔다. 소비 스킬(`h5_add_images`/`h5_report`/`view_task`/`replay_h5`/`ee_verify`/`h5_to_lerobot`; `h5_to_media`는 h5_report의 렌더 라이브러리, `ee_convert`는 EE 변환 라이브러리)은 태스크 이름을 모르고 약속만 따르므로, 새 task를 추가해도 **소비자 코드는 안 건드린다**. (`ee_verify`/`h5_to_lerobot`도 `tcp_pose`·`label_metadata` 약속만 쓴다.)

1. `scripts/custom_envs.py` 에 `@register_env("<id>", ...)` 환경 클래스:
   - `_load_scene` / `_initialize_episode` / `evaluate` — 씬 구성, 시드 랜덤화, 성공 판정
   - `_get_obs_extra` — **매 스텝 기록할 신호** (반환 dict가 자동으로 데이터셋 `obs/extra` 에 실림)
   - `label_metadata()` *(선택)* — 정수 라벨 → 문자열 사전. `h5_add_images`가 데이터셋 `.json` 에 기록 (코드 없이 라벨 해독). 노출 안 하면 무시됨.
2. `scripts/custom_solutions.py` 에 모션플래닝 솔루션 함수 + `SOLUTIONS` 딕셔너리 등록.
3. `scripts/task_to_h5.py` 의 `CUSTOM_TASKS` 에 task id 추가.
4. **검증**: `python scripts/validate_custom_task.py <id>` — 정적 계약(카메라/tcp_pose/success/등록) + 동적 EE 재현(`task_to_h5→h5_add_images→ee_verify` 작은 규모, WSL). PASS 전엔 "추가 완료"로 보지 않는다.

이 과정을 `/add_custom_task <자연어 설명>` 스킬이 자동화한다 — 가능 여부 판단(고맥락, AI가 루브릭으로 판단·거절) → 위 3파일 구현 → 검증. 수동 추가 때도 동일 계약을 따른다.

새 task 가 반드시 지켜야 할 **계약** (코드로 강제 안 되면 데이터셋 생성은 성공하고 학습/서빙에서 늦게 터짐 — 그래서 `validate_custom_task.py` 가 검사):
- **주 카메라(첫 sensor) = `base_camera`** — `h5_to_lerobot` 이 첫 sensor 를 video 로 집어가고 `new_embodiment_config.py` 가 `base_camera` 를 기대. panda 테이블탑 베이스(`PickCubeEnv` 등) 상속이면 자동.
- **`_get_obs_extra` 에 `tcp_pose`** — ④ EE 분기 전체의 생명줄.
- **`evaluate()` 가 `{"success": ...}`** — 성공의 ground truth (검증·라벨·평가가 읽음).

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
- EE 경로(④)는 `pinocchio` 없이 동작 — `ee_convert`(순수 numpy 쿼터니언 수학)로 관절→EE 변환하고, 역변환(EE→관절)은 `_wsl_ee_verify`가 **mplib IK**(WSL)로 푼다. `pinocchio`는 numpy≥2를 요구해 mplib의 `numpy<2`와 충돌하므로 도입하지 않음.
- **두 EE 표현이 공존한다 (같은 궤적, 다른 용도)**: ① `episode_joint_to_ee` = 7d **델타** — `ee_verify`의 IK 재현 게이트 전용(EE 모션이 IK로 따라가지는지 검증). ② `episode_to_abs_eef` = **절대 EEF**(xyz+rot6d, 9d) — `h5_to_lerobot`이 GR00T 데이터셋에 저장. GR00T가 `rep=RELATIVE`+`state_key="eef"` 로 절대→상대를 내부 처리하므로 **우리는 절대값을 저장**(미리 델타 만들지 않음).
- `ee_convert.quat_to_rot6d`는 GR00T `pose.py` 컨벤션(**회전행렬 첫 두 행** flatten, Gram-Schmidt 복원)과 일치해야 함 — 안 맞으면 GR00T가 회전을 오해석. round-trip 자체검증으로 ~3e-7 확인됨.
- `_wsl_ee_verify.py`의 IK 목표는 **로봇 base 프레임**으로 변환해 넣어야 함(`_world_to_base`) — world 프레임 그대로 주면 매 스텝 "IK Failed!". 또 델타는 sim의 드리프트하는 현재 pose가 아니라 **기록된 `tcp[t]`** 에 적용해야 재현율이 정상(open-loop 드리프트 배제).
- `ee_verify`는 **소스 데이터셋 h5**에서만 동작 — sim을 에피소드 초기 씬으로 reset하려면 `episode_seed`가 필요한데 LeRobot 출력엔 없다. 그래서 순서는 `ee_verify`(게이트) → `h5_to_lerobot`(포장).
- `h5_to_lerobot`은 `lerobot` 라이브러리 의존 없이 `pyarrow + imageio`로 v2.1 스펙을 직접 작성 — 작동 중인 conda env를 안 건드리려는 의도. modality 키(state: `qpos`/`eef`, action: `eef`/`gripper`)는 새 임베디먼트 data_config(`NEW_EMBODIMENT`, `finetune_new_embodiment`)와 짝이며, action `eef`는 `type=EEF, rep=RELATIVE, format=XYZ_ROT6D, state_key="eef"`. 최종 로드 검증은 클라우드 학습 박스에서.
- `_wsl_ee_verify.py`도 `h5_to_media`와 동일한 **숫자순 키 정렬**(`int(k.split("_")[1])`)에 의존 — `--count` 랜덤 샘플 후에도 숫자순으로 재정렬해 `episode_seed` 인덱싱이 어긋나지 않게 함.
