# cloud/train — GR00T 파인튜닝 파이프라인 (서버리스)

새 임베디먼트(우리 Panda+EEF)는 베이스 GR00T 로는 못 쓴다 — `new_embodiment` head 가
파인튜닝으로만 생기기 때문(`gr00t_policy.py`가 base 모델 거부). 이 번들이 그 파인튜닝을
**Prefect flow** 로 자급식 수행한다.

서빙(`cloud/runpod`)과 **분리된 학습 전용 이미지**. 파드가 부팅 때 스스로:
bootstrap → 데이터셋(HF) → repair → 학습 → 체크포인트 업로드(HF) → **self_terminate**.

## 파일

| 파일 | 역할 |
|---|---|
| `Dockerfile` | thin 이미지 — base + /app COPY + ENTRYPOINT. **루트 컨텍스트 + `-f` 빌드** |
| `entrypoint.sh` | 부팅: bootstrap(gr00t uv venv) + prefect/wandb(시스템 python) + Prefect Cloud + flow 실행 |
| `train_flow.py` | Prefect @flow — load→prepare_dataset→repair→train→upload_checkpoint→self_terminate(finally) |
| `_gr00t_train.py` | gr00t venv 서브프로세스 — `launch_finetune` 조립 재현 + `run(config)`; Discord 콜백 몽키패치 |
| `discord_callback.py` | `Gr00tTrainer` 에 주입되는 진행 콜백(on_step_end → Discord) |
| `options.py` | Pydantic FlowParameters/TrainingOptions (env 라운드트립) |
| `launch_train.py` | 컨트롤러 — .env 비밀 + 파라미터 → flat env → 파드 생성 |

공유(서빙 번들에서 COPY): `bootstrap.sh`, `new_embodiment_config.py`, `utils/discord.py`.

## 의존성 분리 (왜 서브프로세스)

prefect(오케스트레이션)는 **시스템 python**, GR00T 학습은 **gr00t uv venv** 서브프로세스
(`uv run _gr00t_train.py`)로 분리 — prefect 가 gr00t 핀(torch/numpy/transformers)을 오염
안 시키게. Discord 진행 콜백은 그 서브프로세스 안에서 `Gr00tTrainer.__init__` 몽키패치로
주입(HF 공식 on_step_end 콜백 — stdout 파싱 아님). 몽키패치 실패해도 학습은 정상(W&B 유지).

## 모니터링 (서버리스 = 상태를 외부에 영속)

| 채널 | 무엇 | 필요한 .env |
|---|---|---|
| **W&B** | loss/lr 곡선 (실시간) | `WANDB_API_KEY` (+ `WANDB_PROJECT`) — 없으면 자동 off |
| **Discord/PIPELINE** | 학습 시작/완료/실패 + N스텝 진행바 + 업로드 | `PIPELINE_WEBHOOK_URL` — 없으면 skip |
| **Discord/RUNPOD** | 파드/과금 — 자가종료 성공·**종료실패 경보** | `RUNPOD_WEBHOOK_URL` — 없으면 skip |
| **Prefect** | flow/task 상태·재시도·이력 | `PREFECT_API_URL`, `PREFECT_API_KEY` — 없으면 로컬 ephemeral |
| **HF** | 체크포인트 영속 | `HF_TOKEN` + `--hf-output-repo` |

## 빌드/푸시

```
docker build -f cloud/train/Dockerfile -t adwel94/maniskill-gr00t-train:0.1 -t adwel94/maniskill-gr00t-train:latest .
docker push adwel94/maniskill-gr00t-train:0.1 && docker push adwel94/maniskill-gr00t-train:latest
```

## 실행

```
# 연결 테스트용 짧은 학습 (head-only, L40S) — 체크포인트 보존하려면 --hf-output-repo 지정
python cloud/train/launch_train.py --max-steps 500 --hf-output-repo adwel94/gr00t-threecubes-ft

# 본 학습 (전체 튜닝, A100)
python cloud/train/launch_train.py --full --gpu NVIDIA_A100_80GB_PCIE --max-steps 20000 \
    --global-batch-size 32 --hf-output-repo adwel94/gr00t-threecubes-ft
```

기본은 head-only(`tune_projector+tune_diffusion_model`, FinetuneConfig 기본값) → L40S 48GB.
`--full` 은 llm/visual 까지(A100 80GB 권장).

## 학습 후 → 평가(④)

체크포인트가 HF 에 올라가면, 서빙 번들(`cloud/runpod`)로 그 체크포인트를 serve 한 뒤
로컬 WSL `scripts/gr00t_eval.py` 로 롤아웃 → 성공률 측정. (serve 가 base 모델 대신
파인튜닝 체크포인트를 로드하면 `new_embodiment` 가 지원돼 통신/평가가 된다.)
