"""GR00T 파인튜닝 실행기 — Isaac-GR00T uv venv 안에서 `uv run` 으로 호출됨.

train_flow.py(시스템 python, prefect)가 서브프로세스로 부른다. 이렇게 분리해야
prefect 가 gr00t venv 를 오염시키지 않는다. 설정은 env 로 받는다(pydantic 불필요).

핵심: launch_finetune.py 의 `__main__` 조립을 그대로 재현하되(버전 정합), 그 전에
Gr00tTrainer.__init__ 을 몽키패치해 DiscordProgressCallback 을 add_callback 으로 끼운다.
실패해도 학습은 정상 진행(graceful) — W&B 로깅은 그대로.

env: DATASET_DIR, OUTPUT_DIR, BASE_MODEL_PATH, EMBODIMENT_TAG, MODALITY_CONFIG_PATH,
     TUNE_LLM/TUNE_VISUAL/TUNE_PROJECTOR/TUNE_DIFFUSION_MODEL, GLOBAL_BATCH_SIZE,
     GRADIENT_ACCUMULATION_STEPS, LEARNING_RATE, MAX_STEPS, SAVE_STEPS, SAVE_TOTAL_LIMIT,
     NUM_GPUS, DATALOADER_NUM_WORKERS, EPISODE_SAMPLING_RATE, RESUME_FROM_CHECKPOINT,
     USE_WANDB, WANDB_PROJECT, EXPERIMENT_NAME, DISCORD_HOOK_STEPS
"""
import os
import sys

# /app 를 path 에 (utils.discord, discord_callback import 용)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _b(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "t", "yes", "y", "on")


def _i(key: str, default: int) -> int:
    v = os.environ.get(key)
    return int(v) if v not in (None, "") else default


def _f(key: str, default: float) -> float:
    v = os.environ.get(key)
    return float(v) if v not in (None, "") else default


def _s(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v if v not in (None, "") else default


def _inject_discord_callback(run_name: str, hook_steps: int) -> None:
    """Gr00tTrainer.__init__ 몽키패치 → DiscordProgressCallback 주입 (graceful)."""
    try:
        import gr00t.experiment.trainer as gtrainer
        from discord_callback import DiscordProgressCallback

        _orig_init = gtrainer.Gr00tTrainer.__init__

        def _patched_init(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            try:
                self.add_callback(DiscordProgressCallback(run_name, hook_steps))
                print(f"[_gr00t_train] DiscordProgressCallback injected (every {hook_steps} steps)")
            except Exception as e:  # noqa: BLE001
                print(f"[_gr00t_train] discord callback add failed (ignored): {e}")

        gtrainer.Gr00tTrainer.__init__ = _patched_init
    except Exception as e:  # noqa: BLE001
        print(f"[_gr00t_train] monkeypatch skipped (ignored): {e}")


def main() -> None:
    if "LOGURU_LEVEL" not in os.environ:
        os.environ["LOGURU_LEVEL"] = "INFO"

    run_name = _s("EXPERIMENT_NAME", "gr00t-ft")
    hook_steps = _i("DISCORD_HOOK_STEPS", 20)
    _inject_discord_callback(run_name, hook_steps)

    # ---- launch_finetune.py __main__ 재현 (gr00t main 브랜치 기준) ----
    from gr00t.configs.base_config import get_default_config
    from gr00t.configs.finetune_config import FinetuneConfig
    from gr00t.data.embodiment_tags import EmbodimentTag
    from gr00t.experiment.experiment import run
    from gr00t.experiment.launch_finetune import load_modality_config

    ft = FinetuneConfig(
        base_model_path=_s("BASE_MODEL_PATH", "nvidia/GR00T-N1.7-3B"),
        dataset_path=_s("DATASET_DIR", "/workspace/lerobot"),
        embodiment_tag=_s("EMBODIMENT_TAG", "new_embodiment"),
        modality_config_path=_s("MODALITY_CONFIG_PATH", "/app/new_embodiment_config.py"),
        tune_llm=_b("TUNE_LLM", False),
        tune_visual=_b("TUNE_VISUAL", False),
        tune_projector=_b("TUNE_PROJECTOR", True),
        tune_diffusion_model=_b("TUNE_DIFFUSION_MODEL", True),
        global_batch_size=_i("GLOBAL_BATCH_SIZE", 16),
        gradient_accumulation_steps=_i("GRADIENT_ACCUMULATION_STEPS", 1),
        learning_rate=_f("LEARNING_RATE", 1e-4),
        output_dir=_s("OUTPUT_DIR", "/workspace/outputs/gr00t"),
        experiment_name=run_name,
        wandb_project=_s("WANDB_PROJECT", "maniskill-gr00t"),
        save_steps=_i("SAVE_STEPS", 250),
        save_total_limit=_i("SAVE_TOTAL_LIMIT", 2),
        num_gpus=_i("NUM_GPUS", 1),
        dataloader_num_workers=_i("DATALOADER_NUM_WORKERS", 2),
        use_wandb=_b("USE_WANDB", True),
        max_steps=_i("MAX_STEPS", 500),
        episode_sampling_rate=_f("EPISODE_SAMPLING_RATE", 1.0),
        resume_from_checkpoint=_b("RESUME_FROM_CHECKPOINT", False),
    )

    ft.embodiment_tag = EmbodimentTag.resolve(ft.embodiment_tag)
    embodiment_tag = ft.embodiment_tag.value

    if ft.modality_config_path is not None:
        load_modality_config(ft.modality_config_path)

    dataset_paths = [p for p in ft.dataset_path.split(os.pathsep) if p]

    config = get_default_config().load_dict(
        {
            "data": {
                "download_cache": False,
                "datasets": [
                    {
                        "dataset_paths": dataset_paths,
                        "mix_ratio": 1.0,
                        "embodiment_tag": embodiment_tag,
                    }
                ],
            }
        }
    )
    config.load_config_path = None

    config.model.tune_llm = ft.tune_llm
    config.model.tune_visual = ft.tune_visual
    config.model.tune_projector = ft.tune_projector
    config.model.tune_diffusion_model = ft.tune_diffusion_model
    config.model.state_dropout_prob = ft.state_dropout_prob
    config.model.random_rotation_angle = ft.random_rotation_angle
    config.model.color_jitter_params = ft.color_jitter_params
    config.model.extra_augmentation_config = None
    config.model.load_bf16 = False
    config.model.reproject_vision = False
    config.model.model_name = "nvidia/Cosmos-Reason2-2B"
    config.model.backbone_trainable_params_fp32 = True
    config.model.use_relative_action = True

    config.training.experiment_name = ft.experiment_name
    config.training.start_from_checkpoint = ft.base_model_path
    config.training.optim = "adamw_torch"
    config.training.global_batch_size = ft.global_batch_size
    config.training.dataloader_num_workers = ft.dataloader_num_workers
    config.training.learning_rate = ft.learning_rate
    config.training.gradient_accumulation_steps = ft.gradient_accumulation_steps
    config.training.output_dir = ft.output_dir
    config.training.save_steps = ft.save_steps
    config.training.save_total_limit = ft.save_total_limit
    config.training.num_gpus = ft.num_gpus
    config.training.use_wandb = ft.use_wandb
    config.training.max_steps = ft.max_steps
    config.training.weight_decay = ft.weight_decay
    config.training.warmup_ratio = ft.warmup_ratio
    config.training.wandb_project = ft.wandb_project

    config.data.shard_size = ft.shard_size
    config.data.episode_sampling_rate = ft.episode_sampling_rate
    config.data.num_shards_per_epoch = ft.num_shards_per_epoch

    config.training.save_only_model = ft.save_only_model
    config.training.resume_from_checkpoint = ft.resume_from_checkpoint
    config.training.skip_weight_loading = ft.skip_weight_loading

    run(config)


if __name__ == "__main__":
    main()
