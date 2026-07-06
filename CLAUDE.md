# CLAUDE.md — 작업 규칙

## 용어

환경 = task · 행동 = .h5 · ④ = EE(손끝) 데이터셋 경로.

## 협업 규칙 (최우선)

1. **근거로 말한다** — 주장·진단 전 가진 증거로 self-반증(값 대입해 데이터/제어 흐름
   끝까지). 제일 유력한 가설 하나 + 그걸 반증할 가장 싼 테스트. 한 접근 2번 실패, 또는
   사용자가 기술 근거로 2번 반박하면 멈추고 재검산.
2. **과금은 승인, 과금 중단은 자율** — 과금을 *발생*시키는 행동(파드 생성·이미지 push·
   리포 삭제/덮어쓰기)만 실행 전 한 줄 승인. 과금을 *멈추는* 종료(파드 kill)·무과금·가역은
   자율. 단, `plan_create` 계획서가 `approval_mode: pre_approved` 를 선언했으면, 그 계획을
   `plan_run` 으로 실행하는 동안의 파드 생성은 **사전 승인된 것으로 본다** — 봉투는 계획서의
   **유한한 `step_ladder`**(사다리를 다 돌면 종료). 이 예외는 `plan_run` 실행 컨텍스트에 한정 —
   그 밖의 개별 파드 생성은 건건 승인 그대로.
   패키지 설치·도구 대체·스펙 변경도 먼저 승인(작동 중 conda/venv 안 건드림).
   RunPod 파드 운영(생성 전 통독·폴링·진행 리포팅·종료)은 `cloud/RUNPOD_OPS.md` 가 정본 —
   스킬 경유든 스크립트 직접 실행이든 파드를 만들면 따른다.
3. **역할 분담, 못 하는 것만 요청** — 프로그램으로 얻히는 건 직접 얻는다(예: 파드 IP/포트
   = `runpod_client.pod().portMappings`). 진짜 AI가 못 하는 것만 요청: 시크릿·콘솔 로그·승인.
4. **질문 답 ≠ 파일 승인** — 질문에 답하는 것과 파일 수정은 별개. "이렇게 하겠다"고 방식을
   먼저 제안하고, 제안이 승인되면 그때 고친다.
5. **문서는 지금 상태를 긍정형으로, 의존 방향으로 쓴다** — 현재 무엇을 하는지만 적는다
   (과거 경위·사건은 notes 로). "안 됨" 부정 대신 "~한다"로 우회법을 쓴다. 참조는 의존하는
   아래로만 — 하위 문서가 상위(그걸 쓰는 문서)를 가리키면 순환이다.
6. **작업 시작 전 README 를 읽는다** — 파이프라인 순서·게이트는 README 에 있다. 실행 경로를
   기억으로 재구성하지 말고 README 로 확인하고 시작한다.

## 환경 가정

명령 실행에 필요한 운영 사실. (pip 의존성 = `requirements.txt`, 부트스트랩 절차 = SETUP.md.)

**macOS (Apple Silicon)** (소비 파이프라인 + `ee_verify`·`gr00t_eval` 네이티브) — conda env
`maniskill`, Python `/opt/homebrew/Caskroom/miniconda/base/envs/maniskill/bin/python`.
시뮬 **CPU 백엔드**, 렌더 **MoltenVK**(Vulkan→Metal; ICD 지정은 `scripts/__init__.py`).
IK 는 **pinocchio** 네이티브 — WSL 계층 없이 같은 env 인프로세스로 돈다(`scripts/ik_exec.py`
가 백엔드를 가용성으로 선택). **`task_to_h5` 미지원** — mplib *모션 플래너*(충돌회피
경로계획) 의존이라 새 궤적 생성은 Windows+WSL 또는 Linux 박스에서 한다.

**Windows** (소비 파이프라인 + task_to_h5 오케스트레이션) — conda env `maniskill`,
Python `C:\Users\hun41\miniconda3\envs\maniskill\python.exe`. 시뮬·렌더 모두 **CPU 백엔드**.
pip 의존성은 `requirements.txt`(단일 출처).
**`pinocchio` 미설치** → 라이브 EE 컨트롤(`pd_ee_delta_pose`)·텔레오퍼레이션 미지원
(④는 오프라인 변환 + WSL mplib IK 로 우회).

**WSL** (`task_to_h5`·`ee_verify`·`gr00t_eval` 전용 — `mplib` 이 Linux 전용 바이너리라) —
`Ubuntu-22.04`, Miniconda `maniskill` env(Python 3.10; pip 의존성 `requirements.txt`),
Python `/root/miniconda3/envs/maniskill/bin/python`. **소프트웨어 Vulkan**(lavapipe ICD
`/usr/share/vulkan/icd.d/lvp_icd.x86_64.json`) — WSL엔 GPU Vulkan 없어 sapien 이 씬을 못
띄움. 위 값은 `task_to_h5.py` 상단 상수(`WSL_DISTRO`/`WSL_PYTHON`/`WSL_VK_ICD`).

## 코드 교차 규칙

repo 전반에 걸치는 두 원칙. (개별 스크립트의 세부 함정은 그 코드 주석에.)

1. **소비 스킬은 환경이 선언한 계약만으로 동작한다** — 태스크는 계속 늘어나므로, 소비
   스킬(`h5_add_images`·`h5_to_lerobot`·`gr00t_eval` 등)에 태스크별 코드를 넣으면 태스크마다
   다 고쳐야 한다. 태스크별 지식은 환경 클래스(`custom_envs.py`) 한 곳에 두고, 환경이
   계약(`base_camera`·`tcp_pose`·`evaluate().success`·`label_metadata`)을 선언하면 소비
   스킬은 태스크 이름도 모른 채 그것만 읽는다 → 새 태스크에도 소비 코드 불변(제1원칙).
   카메라 세트도 같은 원리 — `modality.json`에서 발견해 따르므로 1캠/멀티캠이 코드 변경
   없이 처리된다.
2. **스크립트가 실행의 원천, 스킬은 그 위의 얇은 래퍼** — 일은 `scripts/`가 하고, 각
   스크립트는 두 입구를 가진다: 함수(`run(...)`, 다른 코드가 import해 조합)와 CLI
   (`python script.py --옵션`, 터미널·스킬이 호출). 스킬(`.claude/skills/…`)은 그 CLI를
   감싸 호출법만 적은 래퍼일 뿐 로직이 없다. 새 옵션은 함수·CLI 두 입구에 똑같이 반영한다
   — 한쪽만 고치면 "CLI엔 있는데 import하면 없다" 식으로 조용히 어긋난다.
