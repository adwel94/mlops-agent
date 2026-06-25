"""GR00T 학습 파드 컨트롤러 (safari 컨트롤러 역할).

설정/비밀을 flat env vars 로 만들어 학습 이미지 파드를 띄운다. 파드 entrypoint 가
부팅 때 bootstrap → Prefect flow(prepare→repair→train→upload→self_terminate)를 자급 실행.
비밀(HF_TOKEN/WANDB/PREFECT/Discord/RUNPOD_API_KEY)은 프로젝트 .env 에서 주입.

  - CLI:  python cloud/train/launch_train.py --max-steps 500 --hf-output-repo adwel94/gr00t-threecubes-ft
          python cloud/train/launch_train.py --full --gpu NVIDIA_A100_80GB_PCIE --max-steps 20000 ...
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))   # project root (scripts.*)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "runpod"))  # runpod_client
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.env_config import load_env  # noqa: E402
from runpod_client import CloudType, GPUType, create, pod  # noqa: E402

load_env()

DEFAULT_IMAGE = "adwel94/maniskill-gr00t-train:latest"
DEFAULT_GPU = GPUType.NVIDIA_L40S          # head-only 학습엔 충분; --full 은 A100 권장
DEFAULT_VOLUME_GB = 80                     # 모델+데이터셋+outputs/checkpoints
DEFAULT_DISK_GB = 40
DEFAULT_PORTS = ["8888/http", "22/tcp"]    # 서빙 아님 → 5555 불필요

# .env → 파드로 그대로 넘길 비밀/인프라 키 (값 있을 때만).
_SECRET_KEYS = (
    "RUNPOD_API_KEY", "HF_TOKEN",
    "WANDB_API_KEY", "WANDB_PROJECT", "WANDB_ENTITY",
    "PREFECT_API_URL", "PREFECT_API_KEY",
    "RUNPOD_WEBHOOK_URL", "PIPELINE_WEBHOOK_URL", "STDOUT_WEBHOOK_URL",
)
# DISCORD_BOT_TOKEN 은 파드로 보내지 않는다 — 채널을 *읽는* 건 로컬(read_logs.py)뿐.


def _summary(p: dict) -> str:
    return "\n".join(f"  {k}: {p.get(k)}" for k in ("id", "name", "desiredStatus", "costPerHr") if k in p)


def run(
    name: str = "gr00t-train",
    gpu: GPUType | str = DEFAULT_GPU,
    hf_dataset_repo: str = "adwel94/maniskill-threecubes-lerobot",
    hf_output_repo: str | None = None,
    max_steps: int = 500,
    global_batch_size: int = 16,
    learning_rate: float | None = None,
    save_steps: int | None = None,
    num_gpus: int = 1,
    full: bool = False,
    volume: int = DEFAULT_VOLUME_GB,
    container_disk: int = DEFAULT_DISK_GB,
    image: str = DEFAULT_IMAGE,
    cloud_type: CloudType | str = CloudType.SECURE,
) -> str:
    """학습 파드를 생성하고 pod_id 반환. full=True 면 llm/visual 까지 학습(A100 권장)."""
    if isinstance(gpu, str):
        gpu = GPUType[gpu]
    if isinstance(cloud_type, str):
        cloud_type = CloudType[cloud_type]

    env: dict[str, str] = {}
    for k in _SECRET_KEYS:
        v = os.getenv(k)
        if v:
            env[k] = v
    # flow / training params
    env["HF_DATASET_REPO"] = hf_dataset_repo
    if hf_output_repo:
        env["HF_OUTPUT_REPO"] = hf_output_repo
    env["MAX_STEPS"] = str(max_steps)
    env["GLOBAL_BATCH_SIZE"] = str(global_batch_size)
    env["NUM_GPUS"] = str(num_gpus)
    # W&B 키 없으면 use_wandb 끔 (키 없이 wandb.init 이 멈추거나 에러나는 것 방지).
    env["USE_WANDB"] = "true" if os.getenv("WANDB_API_KEY") else "false"
    if learning_rate is not None:
        env["LEARNING_RATE"] = str(learning_rate)
    if save_steps is not None:
        env["SAVE_STEPS"] = str(save_steps)
    if full:
        env["TUNE_LLM"] = "true"
        env["TUNE_VISUAL"] = "true"

    pod_id = create(
        name=name, image_name=image, gpu_id=gpu, gpu_count=num_gpus,
        volume=volume, container_disk=container_disk, cloud_type=cloud_type,
        ports=DEFAULT_PORTS, env=env,
    )
    print(f"[launch_train] pod_id = {pod_id}  (max_steps={max_steps}, full={full}, gpu={gpu.name})")
    print(_summary(pod(pod_id)))
    print(
        "\n파드가 부팅 때 스스로: bootstrap → 데이터셋 → repair → 학습 → 체크포인트 업로드 → 자가종료.\n"
        "  - 진행: Discord(PIPELINE 진행바 / STDOUT raw 로그) + W&B + Prefect Cloud\n"
        "  - 에이전트 모니터링: python cloud/train/read_logs.py  (STDOUT 채널 봇 토큰 조회)\n"
        "  - 실패해도 self_terminate(finally)로 과금 차단. 강제 종료: "
        f"/runpod_down {pod_id}\n"
        + (f"  - 완료 후 체크포인트: https://huggingface.co/{hf_output_repo}\n" if hf_output_repo else
           "  - hf_output_repo 미지정 → 체크포인트는 파드 /workspace 에만(자가종료 시 소멸). 보존하려면 --hf-output-repo 지정.\n")
    )
    return pod_id


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--name", default="gr00t-train")
    p.add_argument("--gpu", default=DEFAULT_GPU.name, help="GPUType 이름 (예: NVIDIA_L40S, NVIDIA_A100_80GB_PCIE)")
    p.add_argument("--hf-dataset-repo", default="adwel94/maniskill-threecubes-lerobot")
    p.add_argument("--hf-output-repo", default=None, help="체크포인트 업로드 대상 (미지정 시 업로드 skip)")
    p.add_argument("--max-steps", type=int, default=500)
    p.add_argument("--global-batch-size", type=int, default=16)
    p.add_argument("--learning-rate", type=float, default=None)
    p.add_argument("--save-steps", type=int, default=None)
    p.add_argument("--num-gpus", type=int, default=1)
    p.add_argument("--full", action="store_true", help="llm+visual 까지 전체 학습 (A100 80GB 권장)")
    p.add_argument("--volume", type=int, default=DEFAULT_VOLUME_GB)
    p.add_argument("--container-disk", type=int, default=DEFAULT_DISK_GB)
    p.add_argument("--image", default=DEFAULT_IMAGE)
    p.add_argument("--cloud-type", default=CloudType.SECURE.name, choices=[c.name for c in CloudType])
    args = p.parse_args()
    run(name=args.name, gpu=args.gpu, hf_dataset_repo=args.hf_dataset_repo,
        hf_output_repo=args.hf_output_repo, max_steps=args.max_steps,
        global_batch_size=args.global_batch_size, learning_rate=args.learning_rate,
        save_steps=args.save_steps, num_gpus=args.num_gpus, full=args.full,
        volume=args.volume, container_disk=args.container_disk, image=args.image,
        cloud_type=args.cloud_type)


if __name__ == "__main__":
    _cli()
