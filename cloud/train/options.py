"""Pydantic 설정 모델 (GR00T 학습 파이프라인).

컨트롤러(launch_train.py)에서 Pydantic → flat env vars 로 파드에 주입하고,
파드 안에서는 env vars → Pydantic 으로 복원한다 (safari_vlm_train options.py 패턴).

필드명 ↔ env 키: 대문자 (예: max_steps → MAX_STEPS, tune_llm → TUNE_LLM).
TrainingOptions 필드는 GR00T FinetuneConfig 와 1:1 (gr00t/configs/finetune_config.py).
"""

import os

from pydantic import BaseModel


class TrainingOptions(BaseModel):
    # --- 경로/임베디먼트 ---
    base_model_path: str = "nvidia/GR00T-N1.7-3B"
    embodiment_tag: str = "new_embodiment"
    modality_config_path: str = "/app/new_embodiment_config.py"
    dataset_dir: str = "/workspace/lerobot"
    output_dir: str = "/workspace/outputs/gr00t"

    # --- 튜닝 범위 (기본 = head-only: projector+diffusion, L40S 가능) ---
    # 전체 학습은 TUNE_LLM=true TUNE_VISUAL=true (A100 80GB 권장).
    tune_llm: bool = False
    tune_visual: bool = False
    tune_projector: bool = True
    tune_diffusion_model: bool = True

    # --- 하이퍼파라미터 (첫 오버핏/연결 테스트용 기본) ---
    global_batch_size: int = 16          # 단일 GPU 합산 배치 (accum 전)
    gradient_accumulation_steps: int = 1
    learning_rate: float = 1e-4
    max_steps: int = 500                 # 테스트용; 본학습은 크게
    save_steps: int = 250                # <= max_steps 라야 체크포인트 산출
    save_total_limit: int = 2
    num_gpus: int = 1
    dataloader_num_workers: int = 2
    episode_sampling_rate: float = 1.0   # 20 에피소드 오버핏 → 전부 사용
    resume_from_checkpoint: bool = False

    # --- 모니터링 ---
    use_wandb: bool = True
    discord_hook_steps: int = 20         # N 스텝마다 Discord 진행바

    @classmethod
    def from_env(cls) -> "TrainingOptions":
        kwargs = {}
        for field_name in cls.model_fields:
            val = os.environ.get(field_name.upper())
            if val is not None and val != "":
                kwargs[field_name] = val
        return cls(**kwargs)


class FlowParameters(BaseModel):
    # --- 데이터/출력 repo ---
    hf_dataset_repo: str = "adwel94/maniskill-threecubes-lerobot"
    hf_output_repo: str = ""             # 비우면 체크포인트 HF 업로드 skip
    hf_output_branch: str = "main"

    # --- 비밀/인프라 (env 에서) ---
    hf_token: str = ""
    runpod_api_key: str = ""
    runpod_pod_id: str = ""              # RunPod 가 파드에 자동 주입
    prefect_api_url: str = ""
    prefect_api_key: str = ""
    wandb_project: str = "maniskill-gr00t"
    wandb_entity: str = ""
    wandb_api_key: str = ""

    training: TrainingOptions = TrainingOptions()

    @classmethod
    def from_env(cls) -> "FlowParameters":
        return cls(
            hf_dataset_repo=os.environ.get("HF_DATASET_REPO", cls.model_fields["hf_dataset_repo"].default),
            hf_output_repo=os.environ.get("HF_OUTPUT_REPO", ""),
            hf_output_branch=os.environ.get("HF_OUTPUT_BRANCH", "main"),
            hf_token=os.environ.get("HF_TOKEN", ""),
            runpod_api_key=os.environ.get("RUNPOD_API_KEY", ""),
            runpod_pod_id=os.environ.get("RUNPOD_POD_ID", ""),
            prefect_api_url=os.environ.get("PREFECT_API_URL", ""),
            prefect_api_key=os.environ.get("PREFECT_API_KEY", ""),
            wandb_project=os.environ.get("WANDB_PROJECT", "maniskill-gr00t"),
            wandb_entity=os.environ.get("WANDB_ENTITY", ""),
            wandb_api_key=os.environ.get("WANDB_API_KEY", ""),
            training=TrainingOptions.from_env(),
        )
