"""GR00T 파인튜닝 Prefect Flow (서버리스 — 파드가 날아가도 상태는 외부에 영속).

[1/6] load_config        — env → FlowParameters
[2/6] prepare_dataset    — HF Hub → /workspace/lerobot
[3/6] repair_metadata    — GR00T repair_lerobot_metadata (stats/relative_stats 재생성)
[4/6] train              — uv run _gr00t_train.py (gr00t venv 서브프로세스; Discord 콜백 주입)
[5/6] upload_checkpoint  — 최종 모델(run-root, 체크포인트 제외) → HF (hf_output_repo 있을 때)
[6/6] self_terminate     — RunPod REST DELETE (finally, 100회 재시도)

이 flow 는 시스템 python(prefect/wandb/hf/requests)에서 돌고, 무거운 학습만 gr00t
uv venv 서브프로세스로 분리해 의존성 충돌을 피한다. 모니터링: Prefect(상태) +
W&B(곡선, 학습 서브프로세스가 직접) + Discord(라이프사이클 + 진행바).
"""

import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import requests
from prefect import flow, task

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from options import FlowParameters  # noqa: E402
from utils.discord import send_discord, DiscordChannel  # noqa: E402

GR00T_DIR = os.environ.get("GR00T_DIR", "/workspace/Isaac-GR00T")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
# uv 가 설치되는 경로를 PATH 에 보장 (bootstrap 이 ~/.local/bin 에 설치).
_ENV_PATH = f"{os.path.expanduser('~/.local/bin')}:{os.path.expanduser('~/.cargo/bin')}:{os.environ.get('PATH', '')}"


def _run(cmd: str, extra_env: dict | None = None) -> None:
    """bash -lc 로 셸 명령 실행 (gr00t venv 의 uv run 등). 실패 시 예외."""
    env = dict(os.environ)
    env["PATH"] = _ENV_PATH
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    print(f"  $ {cmd}", flush=True)
    proc = subprocess.run(["bash", "-lc", cmd], env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed (exit {proc.returncode}): {cmd}")


# ---------------------------------------------------------------------------
# [1/6] load_config
# ---------------------------------------------------------------------------

@task(name="load_config", retries=0)
def load_config() -> FlowParameters:
    print("[1/6] load_config")
    p = FlowParameters.from_env()
    t = p.training
    print(f"  dataset={p.hf_dataset_repo} -> {t.dataset_dir}")
    print(f"  output_repo={p.hf_output_repo or '<skip>'}  output_dir={t.output_dir}")
    print(f"  tune llm/visual/proj/diff = {t.tune_llm}/{t.tune_visual}/{t.tune_projector}/{t.tune_diffusion_model}")
    print(f"  max_steps={t.max_steps} batch={t.global_batch_size} lr={t.learning_rate} gpus={t.num_gpus}")
    return p


# ---------------------------------------------------------------------------
# [2/6] prepare_dataset
# ---------------------------------------------------------------------------

@task(name="prepare_dataset", retries=2, retry_delay_seconds=15)
def prepare_dataset(p: FlowParameters) -> None:
    print(f"[2/6] prepare_dataset — HF {p.hf_dataset_repo} -> {p.training.dataset_dir}")
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=p.hf_dataset_repo,
        repo_type="dataset",
        local_dir=p.training.dataset_dir,
        token=p.hf_token or None,
    )
    print("  dataset ready")


# ---------------------------------------------------------------------------
# [3/6] repair_metadata
# ---------------------------------------------------------------------------

@task(name="repair_metadata", retries=1, retry_delay_seconds=10)
def repair_metadata(p: FlowParameters) -> None:
    print("[3/6] repair_metadata — stats/relative_stats 재생성")
    _run(
        f'cd "{GR00T_DIR}" && uv run python scripts/repair_lerobot_metadata.py '
        f'"{p.training.dataset_dir}" --embodiment-tag {p.training.embodiment_tag}'
    )


# ---------------------------------------------------------------------------
# [4/6] train
# ---------------------------------------------------------------------------

@task(name="train", retries=0)
def train(p: FlowParameters) -> None:
    t = p.training
    pod_id = p.runpod_pod_id or "local"
    run_name = _run_name(p)   # = experiment_name → upload 시 _final_model_dir 와 동일 경로
    print("[4/6] train — uv run _gr00t_train.py (gr00t venv)")
    send_discord(
        f"📚 *[train] 학습 시작* `{run_name}`\n"
        f"steps={t.max_steps} batch={t.global_batch_size} "
        f"tune(proj/diff/llm/visual)={t.tune_projector}/{t.tune_diffusion_model}/{t.tune_llm}/{t.tune_visual}\n"
        f"pod=`{pod_id}`",
        channel=DiscordChannel.PIPELINE,
    )

    # 학습 서브프로세스에 넘길 env (TrainingOptions 필드 → 대문자 키).
    extra = {k.upper(): v for k, v in t.model_dump().items()}
    extra["EXPERIMENT_NAME"] = run_name
    extra["WANDB_PROJECT"] = p.wandb_project
    if p.wandb_entity:
        extra["WANDB_ENTITY"] = p.wandb_entity

    _run(f'cd "{GR00T_DIR}" && uv run python "{APP_DIR}/_gr00t_train.py"', extra_env=extra)

    send_discord(f"✅ *[train] 학습 완료* `{run_name}`\noutput=`{t.output_dir}`\npod=`{pod_id}`",
                 channel=DiscordChannel.PIPELINE)


# ---------------------------------------------------------------------------
# [5/6] upload_checkpoint
# ---------------------------------------------------------------------------

def _run_name(p: FlowParameters) -> str:
    return f"gr00t-ft-{p.runpod_pod_id or 'local'}"


def _has_weights(d: Path) -> bool:
    return d.is_dir() and any(d.glob("*.safetensors"))


def _final_model_dir(output_dir: str, run_name: str) -> str | None:
    """업로드할 **깔끔한 최종 모델** 디렉토리를 찾는다.

    GR00T `run()` 은 `trainer.save_model()` 로 최종 모델(config+가중치+experiment_cfg+processor)을
    `output_dir/experiment_name/` 에 저장한다(체크포인트와 별개). 그걸 우선 쓰고, 없으면
    최신 checkpoint-* 로 폴백. 체크포인트 자체는 upload 시 ignore_patterns 로 제외한다.
    """
    base = Path(output_dir)
    run_root = base / run_name
    # 1) GR00T 최종 모델 (output_dir/experiment_name) — 가중치 포함 확인
    if _has_weights(run_root):
        return str(run_root)
    # 2) output_dir 자체에 최종 모델이 있는 경우 (experiment_name 미사용)
    if _has_weights(base):
        return str(base)
    # 3) 폴백: 최신 checkpoint-* (run_root 우선)
    for parent in (run_root, base):
        ckpts = sorted(
            (d for d in parent.glob("checkpoint-*") if d.is_dir()),
            key=lambda d: int(d.name.split("-")[1]) if d.name.split("-")[1].isdigit() else -1,
        )
        if ckpts:
            return str(ckpts[-1])
    return None


@task(name="upload_checkpoint", retries=2, retry_delay_seconds=15)
def upload_checkpoint(p: FlowParameters) -> None:
    if not p.hf_output_repo:
        print("[5/6] upload_checkpoint — skip (hf_output_repo 미설정)")
        return
    pod_id = p.runpod_pod_id or "local"
    model_dir = _final_model_dir(p.training.output_dir, _run_name(p))
    if not model_dir:
        send_discord(f"⚠️ *[upload] 최종 모델 없음* `{p.training.output_dir}`\npod=`{pod_id}`",
                     channel=DiscordChannel.PIPELINE)
        raise FileNotFoundError(f"no final model/checkpoint under {p.training.output_dir}")
    print(f"[5/6] upload_checkpoint — {model_dir} -> {p.hf_output_repo}@{p.hf_output_branch} (체크포인트 제외)")
    send_discord(f"📤 *[upload] 최종 모델 업로드 시작*\n`{model_dir}` → `{p.hf_output_repo}`\npod=`{pod_id}`",
                 channel=DiscordChannel.PIPELINE)

    from huggingface_hub import HfApi

    api = HfApi(token=p.hf_token or None)
    api.create_repo(p.hf_output_repo, exist_ok=True)
    if p.hf_output_branch != "main":
        api.create_branch(repo_id=p.hf_output_repo, branch=p.hf_output_branch, exist_ok=True)
    # 체크포인트(재시도 전용)·resume 상태는 제외 → repo 엔 서빙 가능한 최종 모델만.
    api.upload_folder(
        folder_path=model_dir,
        repo_id=p.hf_output_repo,
        revision=p.hf_output_branch,
        ignore_patterns=["checkpoint-*", "checkpoint-*/*", "optimizer.pt", "scheduler.pt", "rng_state*.pth"],
        commit_message=f"GR00T finetune final model (max_steps={p.training.max_steps})",
    )
    url = f"https://huggingface.co/{p.hf_output_repo}/tree/{p.hf_output_branch}"
    print(f"  uploaded -> {url}")
    send_discord(f"✅ *[upload] 완료*\n{url}\npod=`{pod_id}`", channel=DiscordChannel.PIPELINE)


# ---------------------------------------------------------------------------
# [6/6] self_terminate
# ---------------------------------------------------------------------------

@task(name="self_terminate", retries=0)
def self_terminate(p: FlowParameters) -> None:
    pod_id, api_key = p.runpod_pod_id, p.runpod_api_key
    print(f"[6/6] self_terminate — pod={pod_id}")
    if not pod_id or not api_key:
        print("  RUNPOD_POD_ID/API_KEY 없음 — skip")
        return
    for attempt in range(1, 101):
        try:
            resp = requests.delete(
                f"https://rest.runpod.io/v1/pods/{pod_id}",
                headers={"Authorization": f"Bearer {api_key}"}, timeout=30,
            )
            resp.raise_for_status()
            send_discord(f"🗑️ Pod 자가종료 성공 [{attempt}] — `{pod_id}`", channel=DiscordChannel.RUNPOD)
            print(f"  deleted (attempt {attempt})")
            time.sleep(30)
            return
        except Exception as e:  # noqa: BLE001
            print(f"  [{attempt}] delete failed: {e}")
            time.sleep(30)
    send_discord(f"🚨 Pod 자가종료 100회 실패! 수동 확인 — `{pod_id}`", channel=DiscordChannel.RUNPOD)


# ---------------------------------------------------------------------------
# flow
# ---------------------------------------------------------------------------

def _flow_run_name() -> str:
    return f"gr00t-ft-{os.environ.get('RUNPOD_POD_ID', 'local')}"


@flow(name="gr00t-finetune", flow_run_name=_flow_run_name, log_prints=True)
def train_flow():
    p = None
    try:
        p = load_config()
        pod_id = p.runpod_pod_id or "local"
        if p.hf_token:
            try:
                from huggingface_hub import login
                login(token=p.hf_token)
            except Exception as e:  # noqa: BLE001
                print(f"  hf login failed (env HF_TOKEN fallback): {e}")
        send_discord(
            f"🚀 *GR00T 학습 시작*\ndataset=`{p.hf_dataset_repo}` steps={p.training.max_steps}\npod=`{pod_id}`",
            channel=DiscordChannel.PIPELINE,
        )

        prepare_dataset(p)
        repair_metadata(p)
        train(p)
        upload_checkpoint(p)

        send_discord(f"✅ *GR00T 학습 파이프라인 완료*\npod=`{pod_id}`", channel=DiscordChannel.PIPELINE)
        print("ALL DONE")
    except Exception as e:
        traceback.print_exc()
        pod_id = p.runpod_pod_id if p else os.environ.get("RUNPOD_POD_ID", "?")
        send_discord(f"❌ *GR00T 학습 실패*\npod=`{pod_id}`\n```{e}```", channel=DiscordChannel.PIPELINE)
        raise
    finally:
        if p:
            self_terminate(p)


if __name__ == "__main__":
    train_flow()
