# cloud/train — GR00T 파인튜닝 파이프라인 (서버리스)

GR00T-N1.7-3B 를 우리 임베디먼트(Panda+EEF)로 파인튜닝하는 학습 전용 이미지. 파드가 부팅 때
스스로: bootstrap → 데이터셋(HF) → repair → 학습 → 체크포인트 업로드(HF) → self_terminate.
Prefect flow 로 오케스트레이션.

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

공유(`cloud/common` 에서 COPY): `bootstrap.sh`, `new_embodiment_config.py`, `utils/discord.py`, `_log_shipper.py`.

## 의존성 분리 (왜 서브프로세스)

prefect(오케스트레이션)는 **시스템 python**, GR00T 학습은 **gr00t uv venv** 서브프로세스
(`uv run _gr00t_train.py`)로 분리 — prefect 가 gr00t 핀(torch/numpy/transformers)을 오염
안 시키게. Discord 진행 콜백은 그 서브프로세스 안에서 `Gr00tTrainer.__init__` 몽키패치로
주입(HF 공식 on_step_end 콜백 — stdout 파싱 아님). 몽키패치 실패해도 학습은 정상(W&B 유지).

## 빌드/푸시

```
docker build -f cloud/train/Dockerfile -t adwel94/maniskill-gr00t-train:0.2 -t adwel94/maniskill-gr00t-train:latest .
docker push adwel94/maniskill-gr00t-train:0.2 && docker push adwel94/maniskill-gr00t-train:latest
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
