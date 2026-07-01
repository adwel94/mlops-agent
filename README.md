# ManiSkill 하네스 (Windows)

[ManiSkill3](https://www.maniskill.ai) 위에서 VLA(Vision-Language-Action) 학습용 데이터셋을
만들고, 선택적으로 [GR00T-N1.7-3B](https://huggingface.co/nvidia/GR00T-N1.7-3B) 를
파인튜닝·평가하는 Windows용 하네스.

핵심 개념 두 개로 요약된다 — **환경 = task**, **행동 = .h5**.

```
task 환경  →  행동 궤적(.h5)  →  이미지 입힌 데이터셋(.h5)  →  (선택) GR00T 파인튜닝·평가
```

task 환경에서 로봇 팔의 행동 궤적(.h5)을 만들고, 거기에 카메라 이미지를 입혀 (이미지 + 액션)
데이터셋을 만든다. 만드는 모든 산출물(궤적·데이터셋·미디어)은 프로젝트 안
`data/datasets/<task>/` 에 떨어지고 `.gitignore` 대상이라, git엔 코드·레시피만 남고 다른
환경에서 그대로 재현된다. 각 작업은 **슬래시 커맨드 / Python 함수 / CLI / Jupyter 노트북**
어느 방식으로든 동일하게 호출된다.

## 기술 스택

이 하네스가 얹혀 있는 외부 기술과, 여기서 각자가 맡는 역할:

| 기술 | 여기서 하는 일 |
|---|---|
| [ManiSkill3](https://www.maniskill.ai) | 시뮬레이션 환경·빌트인 task·panda 모션플래닝 데모의 토대 |
| [SAPIEN](https://sapien.ucsd.edu) | ManiSkill 아래의 물리·렌더 엔진 (뷰어·이미지 렌더) |
| [mplib](https://github.com/haosulab/MPlib) | 모션플래닝·IK 솔버 — 궤적 생성(`task_to_h5`)과 EE 실행(`ee_verify`·`gr00t_eval`). Linux 전용이라 WSL에서 구동 |
| Mesa lavapipe (Vulkan) | WSL엔 GPU Vulkan이 없어, sapien이 씬을 띄우는 소프트웨어 렌더 백엔드 |
| PyTorch · gymnasium · h5py | 런타임 — 텐서 · 환경 API · 데이터셋 저장(HDF5) |
| pyarrow · imageio | LeRobot 출력의 parquet·mp4 기록 (`h5_to_lerobot`) |
| [GR00T-N1.7-3B](https://huggingface.co/nvidia/GR00T-N1.7-3B) (NVIDIA) | 파인튜닝 대상 VLA 파운데이션 모델 |
| [LeRobot v2.1](https://github.com/huggingface/lerobot) · [Isaac-GR00T](https://github.com/NVIDIA/Isaac-GR00T) | GR00T 학습 데이터 포맷·규약 (meta 스키마·임베디먼트 config의 기준) |
| [Hugging Face Hub](https://huggingface.co) | 데이터셋·모델 저장/배포 |
| [RunPod](https://runpod.io) | 파인튜닝·서빙용 GPU 클라우드 파드 |
| [Prefect](https://prefect.io) | 학습 파드가 부팅 때 스스로 도는 flow 오케스트레이션 |
| [Weights & Biases](https://wandb.ai) | 학습 로깅 |
| Discord | 학습 파드 진행 리포트 (PIPELINE·STDOUT 채널 + AI 리포트) |
| Cloudflare Workers | 파드 종료를 RunPod 밖에서 보장하는 reaper (`cloud/reaper`) |
| ZMQ · msgpack | 정책 서버(GPU 파드) ↔ 롤아웃 클라이언트(WSL) 통신 |

## 스킬과 원천 스크립트

각 스킬은 **슬래시 커맨드 / Python 함수 / CLI** 세 방식으로 동일하게 호출된다 (로컬 스킬은
추가로 `notebooks/<skill>.ipynb` 사용 예제 포함). 일은 원천 스크립트가 하고, 스킬(`.claude/skills/`)은
그 CLI를 감싼 얇은 래퍼다.

### ① 데이터셋 만들기 (Windows, 무과금)

행동 궤적을 얻어 → 이미지를 입혀 데이터셋으로 → (GR00T용) EE 규약으로 변환·업로드한다.
행동을 받아오든 직접 풀든 형식이 같아 `/h5_add_images` 이후 단계는 전부 공유된다.

```
/fetch_sample_h5·/task_to_h5  →  /h5_add_images  →  /ee_verify  →  /h5_to_lerobot  →  /hf_push_dataset
   (받기 / 직접 생성)              (이미지 입힘)      (EE 게이트)     (GR00T 변환)       (HF 업로드)
                                    └ 품질 점검: /h5_report
```

| 스킬 | 원천 스크립트 | 하는 일 |
|---|---|---|
| `/fetch_sample_h5` | `scripts/fetch_sample_h5.py` | 공식 데모 행동 궤적 다운로드 |
| `/task_to_h5` | `scripts/task_to_h5.py` (WSL) | 모션플래닝으로 행동 궤적 직접 생성 |
| `/h5_add_images` | `scripts/h5_add_images.py` | 궤적을 리플레이하며 카메라 이미지 입힘 → 데이터셋 |
| `/h5_report` | `scripts/h5_report.py` | 데이터셋 품질 리포트 (MD + 필름스트립 + mp4) |
| `/ee_verify` | `scripts/ee_verify.py` (WSL) | EE-델타를 IK로 재현하는 게이트 (GR00T 변환 전 방법 확정) |
| `/h5_to_lerobot` | `scripts/h5_to_lerobot.py` | 데이터셋 → GR00T LeRobot v2.1 (절대 EEF 10d) 변환 |
| `/hf_push_dataset` | `scripts/hf_push_dataset.py` | LeRobot 디렉토리 → HF Hub 업로드 + 구조 검증 |

### ② 학습·평가 (RunPod GPU, ⚠️ 과금)

①의 데이터셋으로 실제 GPU에서 파인튜닝하고, 정책을 sim에 붙여 태스크 성공률을 잰다.
실제 자원을 켜는 작업이라 명시 요청 시에만 실행하고, 끝나면 `/runpod_down` 으로 종료한다.

```
/gr00t_train  →  /gr00t_serve  →  /gr00t_eval         (파드 운영: /runpod_up · /runpod_ls · /runpod_down)
  (파인튜닝)        (정책 서버)       (sim 성공률)
```

| 스킬 | 원천 스크립트 | 하는 일 |
|---|---|---|
| `/gr00t_train` | `cloud/train/launch_train.py` | HF 데이터셋으로 GR00T 파인튜닝 → 최종 모델만 HF 업로드 (자가종료) |
| `/gr00t_serve` | `cloud/serve/serve_up.py` | 파인튜닝 모델을 정책 서버(5555/tcp)로 서빙 |
| `/gr00t_eval` | `scripts/gr00t_eval.py` (WSL) | 정책을 sim에 붙여 닫힌 루프 롤아웃 → 태스크 성공률 |
| `/runpod_up` | `cloud/runpod/runpod_up.py` | 범용 GPU 파드 생성 (serve의 하위 기반) |
| `/runpod_ls` | `cloud/runpod/runpod_ls.py` | 떠 있는 파드 + 시간당 비용 (읽기 전용) |
| `/runpod_down` | `cloud/runpod/runpod_down.py` | 파드 종료 (과금 차단) |

### ③ 기타 도구 (Windows, 무과금)

파이프라인 본선은 아니지만 받쳐주는 것들 — 둘러보기·헬스체크·새 task 추가.

| 스킬 | 원천 스크립트 | 하는 일 |
|---|---|---|
| `/view_task` | `scripts/view_task.py` | SAPIEN 데스크탑 뷰어로 환경 둘러보기 |
| `/replay_h5` | `scripts/replay_h5.py` | 저장된 에피소드 재생 |
| `/check_maniskill_env` | `scripts/check_maniskill_env.py` | 환경 검증 + 복구 (`--fix` 로 requirements.txt 설치, 못 하는 건 제안) |
| `/add_custom_task` | `scripts/custom_envs.py` · `custom_solutions.py` · `validate_custom_task.py` | 새 커스텀 task를 계약에 맞춰 추가 (소비 스킬은 불변) |

## 더 보기

- **pip 의존성** (단일 출처) → [`requirements.txt`](requirements.txt) — 설치·검증은 `/check_maniskill_env --fix`
- **환경 세팅** (conda env 생성 · WSL 준비 · 시크릿 = 매니페스트로 못 담는 절차) → [`SETUP.md`](SETUP.md)
- **작업 여정·히스토리** (성능 진단 · 손목캠 구현 · 클라우드 운영 로그) → [`notes/`](notes/README.md)
- **협업 규칙·환경 가정** → [`CLAUDE.md`](CLAUDE.md)
- **GR00T 학습 배경** (LeRobot 데이터셋 구조, 한 row의 의미) → `notebooks/gr00t_n17_training_explained.ipynb`
- **커스텀 task 추가** → `/add_custom_task` 스킬
