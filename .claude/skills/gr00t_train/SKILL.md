---
name: gr00t_train
description: HF Hub 의 LeRobot 데이터셋으로 GR00T-N1.7-3B 를 파인튜닝하는 RunPod 학습 파드를 띄운다. cloud/train/launch_train.py 래퍼 — 설정/비밀을 flat env 로 만들어 학습 이미지(maniskill-gr00t-train) 파드를 생성하고, 파드 entrypoint 가 부팅 때 bootstrap → Prefect flow(prepare→repair→train→upload→self_terminate)를 자급 실행한다. 학습 후 최종 모델만 HF Hub 로 업로드(체크포인트 제외)하고 파드는 자가종료(과금 차단). RUNPOD_API_KEY/HF_TOKEN 환경변수 필요. args는 `[--max-steps N] [--hf-output-repo REPO] [--hf-dataset-repo REPO] [--gpu GPUType이름] [--global-batch-size N] [--learning-rate LR] [--save-steps N] [--num-gpus N] [--full] [--cloud-type COMMUNITY|SECURE]`; 비어있으면 max-steps=500, dataset=adwel94/maniskill-threecubes-lerobot, gpu=NVIDIA_L40S, head-only. 실제 GPU 파드를 켜는(=과금) 작업이므로 사용자가 명시 요청했을 때만 실행.
---

# gr00t_train — GR00T 파인튜닝 학습 파드 생성 (④)

`cloud/train/launch_train.py` 래퍼. HF Hub 의 LeRobot v2.1 데이터셋으로 GR00T-N1.7-3B 를 파인튜닝한다. 파드는 부팅 때 SSH 없이 스스로: **bootstrap → 데이터셋 다운로드 → repair(stats 재생성) → 학습 → 최종 모델 HF 업로드 → 자가종료**. 비밀(HF_TOKEN/WANDB/PREFECT/Discord/RUNPOD_API_KEY)은 `.env` 에서 주입.

서빙 이미지와 **다른 전용 이미지**(`maniskill-gr00t-train`)를 쓰고, Prefect flow 로 단계를 오케스트레이션한다. 실패해도 `self_terminate`(finally)로 과금이 차단된다.

> **과금 주의**: 실제 GPU 파드를 켜는 외부 작업이다. 사용자가 명시적으로 요청했을 때만 실행. 자가종료가 기본이지만 행(hang) 대비 `/runpod_ls` 로 확인하고 필요 시 `/runpod_down`.

## 전제조건

- `RUNPOD_API_KEY`, `HF_TOKEN` 환경변수 (.env 자동 로드).
- 데이터셋이 HF Hub 에 LeRobot v2.1 로 올라가 있어야 함 (`/hf_push_dataset` 산출물).
- (선택) `WANDB_API_KEY` 있으면 W&B 로깅 자동 on; 없으면 끔.

## 호출됐을 때

1. `args` 파싱 (모두 선택):
   - `--max-steps <N>` (기본 500 — 디버그/스모크 규모; 본 학습은 수천~수만)
   - `--hf-output-repo <REPO>` — 학습 결과 업로드 대상 (미지정 시 파드 내부에만 = 자가종료 시 소멸)
   - `--hf-dataset-repo <REPO>` (기본 `adwel94/maniskill-threecubes-lerobot`)
   - `--gpu <GPUType 이름>` (기본 `NVIDIA_L40S`; head-only 면 충분, `--full` 은 A100 권장)
   - `--global-batch-size`(기본 16), `--learning-rate`, `--save-steps`, `--num-gpus`(기본 1)
   - `--full` — llm+visual 까지 전체 학습 (A100 80GB 권장)
   - `--cloud-type COMMUNITY|SECURE` (기본 SECURE)
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe cloud\train\launch_train.py [옵션]
   ```
3. 출력: `pod_id`, 상태/비용 요약, 진행 모니터링 경로(Discord/W&B/Prefect, `read_logs.py`).

## 동작 / 주의사항

- **최종 모델만 업로드** — 학습 완료 후 repo 루트에 config + *.safetensors 형상으로 올림(체크포인트 `checkpoint-*` 는 제외). 그래서 `/gr00t_serve <output-repo>` 로 바로 서빙 가능.
- 체크포인트는 학습 *재시도* 전용(중간 실패 복구) — 정상 완료 시 최종 모델만 필요. 파드 내 `save_total_limit` 로 자동 회전.
- 진행 모니터링: Discord(PIPELINE 진행바 / STDOUT raw 로그) + W&B + Prefect Cloud. 에이전트는 `python cloud/train/read_logs.py` 로 STDOUT 채널 조회(봇 토큰, 로컬 전용).
- 외부 상태(콘솔/대시보드 로그)는 직접 긁지 말고 필요하면 사용자에게 요청 (CLAUDE.md 협업 규칙).
- `--hf-output-repo` 미지정 시 결과가 보존되지 않으니, 보존하려면 반드시 지정.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/gr00t_train --max-steps 500 --hf-output-repo adwel94/gr00t-threecubes-ft` | 디버그 규모 head-only 학습 → HF 업로드 |
| `/gr00t_train --full --gpu NVIDIA_A100_80GB_PCIE --max-steps 20000 --hf-output-repo adwel94/gr00t-threecubes-ft` | 본 학습(전체 튜닝, A100) |

흐름: `/hf_push_dataset`(데이터셋) → **`/gr00t_train --hf-output-repo R`** → `/gr00t_serve R` → (평가) → `/runpod_down`.
