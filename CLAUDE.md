# ManiSkill 하네스 — 작업 지침 (CLAUDE.md)

[ManiSkill3](https://www.maniskill.ai) 위 Windows VLA 데이터셋 하네스. 핵심 개념: **환경 = task**, **행동 = .h5**.

**이 문서 = "이 repo에서 어떻게 일하는가"** (협업 규칙·환경 전제·계약·코드 불변식). 하네스 **사용법**(흐름·스킬·명령어·파일 포맷·지원 태스크·클라우드 운영)은 [`README.md`](README.md)가 단일 출처, 클라우드 세부는 `cloud/*/README.md`, 진단 이력은 `notes/`. **사용법을 여기 다시 쓰지 말 것 — README를 갱신하고 가리킨다.**

## 협업 규칙 (다른 모든 지침과 함께 우선)

**기본 자세** — "다음 단계를 굴리기"가 아니라 "올바른 것을 만들기". 성공 = "동작했다"가 아니라 **"약속한 산출물이 무결하게 나왔다"**. 막히면 통과시키지 말고 무엇이 왜 막혔는지부터 드러내라.

**핵심 게이트 — 우회 전에 분류한다.** 에러·누락·이상을 만나면 손대기 전 한 번 분류:
- **환경 quirk** (산출물과 무관한 실행환경 마찰 — 인코딩·경로·권한·누락 패키지 등) → 인라인으로 고치고 진행, 무엇을 고쳤는지 한 줄 남김.
- **결함(defect)** (만드는 것/약속한 산출물이 잘못됐다는 신호 — 파일 없음·형태 다름·스펙 불일치·불완전) → **멈춘다. 우회 금지.** 헤드라인으로 보고하고 결정을 받는다.
- 확신 안 서면 **결함으로 취급**(안전한 쪽).

**산출물 무결성** — "로드/실행되나?"가 아니라 **"이 단계가 내놓기로 한 걸 온전히 냈나?"**. 다음 단계 입력으로 쓰기 전 기대 형태와 대조. 불일치 = 결함 = 멈춤.

**결함 보고 순서** — ① 결함을 첫 문장으로. ② 근본 원인은 아는 만큼만, 모르면 모른다고(추측을 사실로 포장 금지). ③ 우회로는 "이건 우회다" 라벨 붙여 옵션으로만, 기본 추천은 항상 "고친다". ④ 사용자가 고르기 전 우회 진행 금지.

**추론 규율** (주장·진단할 때) —
- 가설은 리스트로 깔지 말고 **제일 유력한 하나 + 그걸 반증할 가장 싼 테스트**만. breadth로 depth 흉내내지 말 것.
- 주장 전에 **이미 가진 증거로 self-반증** — 우리가 아는 사실과 충돌 안 하나, 값을 대입해 데이터/제어 흐름을 끝까지 따라가고 단정. 이미 배제되는 후보는 빼고 말한다.
- **사용자가 기술 근거로 2번 반박 = 내 확신 과함의 신호.** 우기지 말고 증거에 재검산.

**멈춤·경계** —
- **시도 예산** — 한 접근이 2번 실패하면 멈추고 보고 후 질문(다른 우회 연쇄 금지).
- **외부 상태는 캐지 말고 요청** — 실행환경 밖(클라우드 콘솔 로그·대시보드·시크릿·파드 내부)은 스스로 긁지 말고 사용자에게. (학습 실패 로그 = GraphQL 삽질 대신 "콘솔 로그 붙여주세요".)
- **조용한 변경 금지** — 패키지 설치·도구 대체·스펙 변경·임시 mock 은 먼저 승인. 작동 중 conda/venv 안 건드림.
- **과금·비가역은 확인 먼저** — RunPod 파드 생성·이미지 push·리포 삭제/덮어쓰기 등은 실행 전 한 줄 확인(빌드처럼 무과금·가역은 진행 가능).
- **역할 분담** — AI = 코드·빌드·로컬 분석 / 사용자 = 시크릿·콘솔 로그·승인.

**모니터링·폴링** (클라우드 작업) —
- AI 자연어 리포트(해석·판단)는 **`#ai-리포팅` 채널로만** (`ai_report.py`; 숫자는 `wandb_status.py` 로 prose 에 녹임) — 파드-push 채널(RUNPOD/PIPELINE/STDOUT)과 분리. 폴링 주기(10~20분)마다 추세 코멘트 1회 OK, 시작·추세변화·완료·이상은 필수, 분 단위 도배 금지.
- 파드 부팅·학습·serve 등 **하네스가 못 추적하는 외부 상태**는 자동 알림이 없으니 직접 폴링: `Bash` `run_in_background` 로 `sleep <N> && <확인>`(확인 = `read_logs.py`/`wandb_status.py`/`runpod_ls.py`) → 끝나면 task-notification 으로 결과 읽고 다음 수 판정. **일회성**(sleep 1 → 확인 1 → 판정)이라 턴 기반; 루프 데몬 금지. 간격: 부팅 5~8분, 학습 10~15분, stall 의심 시 촘촘히. 포그라운드 `sleep` 은 막히므로 백그라운드.

## 환경 가정

명령 실행에 필요한 운영 사실. (설치 레시피는 README "WSL 환경 준비".)

**Windows** (소비 파이프라인 + task_to_h5 오케스트레이션) — conda env `maniskill`, Python `C:\Users\hun41\miniconda3\envs\maniskill\python.exe`. 시뮬·렌더 모두 **CPU 백엔드**. 주요 패키지 `mani_skill 3.0.1`/`sapien 3.0.3`/`torch 2.12.0+cpu`/`h5py`/`gymnasium`. **`pinocchio` 미설치** → 라이브 EE 컨트롤(`pd_ee_delta_pose`)·텔레오퍼레이션 미지원(④ EE 데이터셋은 오프라인 변환 + WSL mplib IK 로 우회).

**WSL** (`task_to_h5`·`ee_verify`·`gr00t_eval` 전용 — `mplib` 이 Linux 전용 바이너리라) — `Ubuntu-22.04`, Miniconda `maniskill` env(Python 3.10, `mplib 0.1.1`, `numpy<2`), Python `/root/miniconda3/envs/maniskill/bin/python`. **소프트웨어 Vulkan**(lavapipe ICD `/usr/share/vulkan/icd.d/lvp_icd.x86_64.json`) — WSL엔 GPU Vulkan 없어 sapien 이 씬을 못 띄움. 위 값은 `task_to_h5.py` 상단 상수(`WSL_DISTRO`/`WSL_PYTHON`/`WSL_VK_ICD`).

## 커스텀 task 계약

제1원칙: **소비 스킬은 태스크 이름을 모른다.** 태스크별 지식은 환경 클래스 하나(`scripts/custom_envs.py`)에만 두고, 소비 스킬(`h5_add_images`/`h5_report`/`view_task`/`replay_h5`/`ee_verify`/`h5_to_lerobot`/`gr00t_eval`)은 아래 계약만 따른다 → 새 task 추가에도 소비자 코드 불변. **태스크별 분기를 소비 스크립트에 절대 넣지 말 것.**

반드시 지킬 **계약** (코드로 강제 안 되면 데이터셋은 생성되고 학습/서빙에서 늦게 터짐 — `validate_custom_task.py` 가 검사):
- **주 카메라 = `base_camera`** — 이름으로 집어가므로 위치 무관(`h5_to_lerobot`/`new_embodiment_config` 이 기대). panda 테이블탑 베이스(`PickCubeEnv` 등) 상속이면 자동. env 가 추가 카메라(예: `panda_wristcam` 의 `hand_camera`)를 선언하면 소비자가 **자동으로 같이 싣는다**(멀티캠은 코드 분기 없이 지원 — "코드 작성 시 유지" 참조).
- **`_get_obs_extra` 에 `tcp_pose`** — ④ EE 분기 전체의 생명줄.
- **`evaluate()` 가 `{"success": ...}`** — 성공의 ground truth.
- *(언어 지시형이면)* **`label_metadata()`** — 정수 라벨 → 문자열 사전. 데이터셋 `.json` 만으로 지시문 해독.

추가 절차(가능 판단 → `custom_envs`/`custom_solutions`/`CUSTOM_TASKS` 구현 → 검증)는 `/add_custom_task` 스킬이 자동화. 수동 추가도 같은 계약·검증. **`validate_custom_task.py <id>` PASS 전엔 "추가 완료"로 보지 않는다.**

## HF 명명·버전 정책

push/train 시 규칙. 반복 재학습/재생성이 repo 를 증식(`-ft2`,`-final`)시키거나 덮어쓰기로 과거를 지우는 걸 막는다: **태스크당 repo 하나 + git 태그로 버전**(HF=git 이라 한 repo 에 스냅샷이 공짜).

```
데이터셋  adwel94/maniskill-<slug>-lerobot   tag v1, v2 ...                       (생성방식 바뀌면 새 태그·불변)
모델      adwel94/gr00t-<slug>               main + tag <ds_ver>-s<steps>[-full]  (예: v1-s3000)
```

- **HF 태그가 버전 진실, 로컬은 작업 사본** — `data/` 는 gitignore+재생성 가능 → 로컬엔 최신 빌드 하나만. 모델은 로컬에 없음(파드→HF 직행).
- **버전 단일 출처 = `MANIFEST.yaml`** (커밋됨) — 어떤 버전이 어디 있고 eval 이 얼마인지 잇는 지도.
- **태그는 불변** — `hf_push_dataset --version v1` 은 중복이면 **에러**(덮어쓰지 않음; 바뀌었으면 새 번호). 모델 태그 충돌은 경고만(main 갱신).
- **자동 기록** — `hf_push_dataset --version`→`add_dataset`, `launch_train`→`add_model`(eval=null). 모델 eval 은 평가 후 수동 `python scripts/manifest.py set-eval <slug> <model> <값>`.
- **slug** = `maniskill-<slug>-lerobot` 에서 추출 → push/train 이 같은 dataset repo 를 알아 MANIFEST 키 일치.
- **학습 이미지는 코드를 담지 데이터를 담지 않는다** — `new_embodiment_config.py` 등 파드 코드를 빌드 시 굽는다(데이터주도라 한 이미지가 1캠·멀티캠 데이터셋 다 학습; 데이터 버전마다 새 이미지 불필요). **이미지 안 코드가 바뀔 때만** 재빌드. 태그 = `:latest`(launch_train 기본) + `:git-<short-sha>`(불변 추적). 학습에 쓴 이미지는 `add_model` 이 MANIFEST 모델 항목 `image` 필드에 기록(데이터=git태그, 모델=HF태그, 이미지=git-sha — 셋 다 불변 추적자). 코드 바꿨으면 재빌드+push 후 그 SHA 태그로 학습.

## 코드 작성 시 유지해야 할 부분

건드리면 조용히 깨지는 불변식. "고치기" 전에 왜 이렇게 됐는지부터 읽을 것.

- **`gym.make` `render_backend='cpu'`** — `h5_add_images` 는 monkey-patch 주입, `view_task`/`replay_h5` 는 호출에 직접 명시. Windows GPU 렌더 경로가 동작 불가.
- **WSL headless 우회** (`_wsl_solve_wrapper`/`_wsl_solve_custom`) — ① `render_backend='cpu'` ② `RenderSystem` 실패 시 인자 없이 재호출(llvmpipe 자동) ③ 호출자 `VK_ICD_FILENAMES`=lavapipe.
- **`h5_add_images` 의 `if __name__=="__main__"` 가드** — Windows `spawn` multiprocessing 이라 없으면 자식 무한 spawn.
- **trajectory 키 = 숫자순 정렬** (`int(k.split("_")[1])`, `h5_to_media`·`_wsl_ee_verify` 둘 다) — 사전순이면 `traj_10`<`traj_2` 로 `--episode`/`episode_seed` 인덱싱 어긋남.
- **`task_to_h5` subprocess `encoding='utf-8', errors='replace'`** — WSL UTF-8(tqdm)을 Windows cp949 로 디코드하면 깨짐.
- **`h5_add_images` 끝 재현율 출력** — 입력 vs 리플레이 success, WSL↔Windows 백엔드 발산 감지용 경고(데이터는 안 지움).
- **소비자는 태스크 이름을 모른다** — 메타데이터는 환경이 선언(`_get_obs_extra`/`label_metadata`), 소비자는 약속만 따름. 태스크별 분기 금지. (`h5_to_media`·`ee_convert` 는 스킬 아닌 라이브러리.)
- **함수 ↔ CLI 동등성** — 새 옵션은 양쪽에 일관 반영.
- **EE 경로(④)는 `pinocchio` 없이** — `ee_convert`(순수 numpy)로 관절→EE, 역변환은 `_wsl_ee_verify` 가 mplib IK(WSL). `pinocchio`(numpy≥2)는 mplib(`numpy<2`)와 충돌하므로 도입 안 함.
- **두 EE 표현 공존** (같은 궤적, 다른 용도): `episode_joint_to_ee`=7d **델타**(`ee_verify` IK 게이트 전용), `episode_to_abs_eef`=**절대 EEF**(xyz+rot6d 9d, `h5_to_lerobot` 저장). GR00T 가 `rep=RELATIVE`+`state_key="eef"` 로 내부 상대화하므로 **절대값을 저장**(미리 델타 X).
- **`ee_convert.quat_to_rot6d` = GR00T `pose.py` 컨벤션** (회전행렬 첫 두 행 flatten, Gram-Schmidt 복원) — 안 맞으면 회전 오해석. round-trip ~3e-7.
- **`_wsl_ee_verify` IK 목표 = 로봇 base 프레임** (`_world_to_base`) — world 그대로면 매 스텝 "IK Failed!". 델타는 sim 의 드리프트 pose 가 아니라 **기록된 `tcp[t]`** 에 적용(open-loop 드리프트 배제).
- **`ee_verify` 는 소스 데이터셋 h5 에서만** — 씬 reset 에 `episode_seed` 필요한데 LeRobot 출력엔 없음. 그래서 `ee_verify`(게이트) → `h5_to_lerobot`(포장) 순서.
- **`h5_to_lerobot` 은 `lerobot` 라이브러리 없이** `pyarrow`+`imageio` 로 v2.1 직접 작성(conda env 안 건드림). modality 키(state `qpos`/`eef`, action `eef`/`gripper`)는 `NEW_EMBODIMENT` data_config 와 짝; action `eef`=`EEF/RELATIVE/XYZ_ROT6D/state_key="eef"`.
- **카메라는 데이터에서 발견**(`modality.json` video 키), 하드코딩 금지 — `h5_to_lerobot`(`select_cameras`)·`new_embodiment_config`(`_discover_video_keys`, DATASET_DIR/meta/modality.json)·`_wsl_gr00t_eval` 이 모두 거기서 읽어 1캠/멀티캠(손목캠) 태스크 무관 처리. 체크포인트는 카메라 수 고정이라 v1(1캠)·v2(2캠)는 HF 태그로 분리(`notes/wrist-camera-scope.md`).
- **손목캠 옵트인 = `h5_add_images --robot-uids panda_wristcam`** — 리플레이 시 gym.make 에 robot 주입(팔 동일 → 액션 그대로, `hand_camera` 만 추가). 쓴 robot 은 출력 사이드카 `env_info.robot_uids` 에 박히고 `ik_exec.make_env_and_solver`·`_wsl_gr00t_eval`·`_wsl_ee_verify`·`_wsl_abs_eef_replay` 가 그걸 읽어 같은 카메라 세트로 env 구성. 기본값 `panda` = 1캠(하위호환).
