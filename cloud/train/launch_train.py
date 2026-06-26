"""GR00T 학습 파드 컨트롤러.

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
DEFAULT_VOLUME_GB = 250                    # 모델 캐시(~17GB) + 3B 체크포인트(~29GB) 여유 충분 (넉넉하게)
DEFAULT_DISK_GB = 80                        # venv(torch/gr00t/flash-attn ~15GB) + 시스템 여유
DEFAULT_PORTS = ["8888/http", "22/tcp"]    # 서빙 아님 → 5555 불필요

# .env → 파드로 그대로 넘길 비밀/인프라 키 (값 있을 때만).
_SECRET_KEYS = (
    "RUNPOD_API_KEY", "HF_TOKEN",
    "WANDB_API_KEY", "WANDB_PROJECT", "WANDB_ENTITY",
    "PREFECT_API_URL", "PREFECT_API_KEY",
    "RUNPOD_WEBHOOK_URL", "PIPELINE_WEBHOOK_URL", "STDOUT_WEBHOOK_URL",
    # 외부 종료 Worker(cloud/reaper) — 파드가 자기 삭제를 RunPod 대신 여기로 요청
    "WORKER_TERMINATE_URL", "POD_PING_SECRET",
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
    save_total_limit: int = 1,
    num_gpus: int = 1,
    full: bool = False,
    task: str | None = None,
    volume: int = DEFAULT_VOLUME_GB,
    container_disk: int = DEFAULT_DISK_GB,
    image: str = DEFAULT_IMAGE,
    cloud_type: CloudType | str = CloudType.SECURE,
) -> str:
    """학습 파드를 생성하고 pod_id 반환. full=True 면 llm/visual 까지 학습(A100 권장).

    hf_dataset_repo 는 `repo` 또는 `repo@<버전태그>` 형식. 버전을 주면 그 태그를 데이터셋
    revision 으로 받고, 모델 태그를 `<버전>-s<steps>[-full]` 로 자동 도출한다(예: v1-s3000).
    hf_output_repo 가 있으면 런치 시 MANIFEST.yaml 에 모델 항목을 eval=null 로 기록한다.
    """
    if isinstance(gpu, str):
        gpu = GPUType[gpu]
    if isinstance(cloud_type, str):
        cloud_type = CloudType[cloud_type]

    # `repo@버전` 분리 → 데이터셋 revision + 모델 태그용 버전 토큰.
    if "@" in hf_dataset_repo:
        ds_repo, ds_rev = hf_dataset_repo.split("@", 1)
    else:
        ds_repo, ds_rev = hf_dataset_repo, ""
    dataset_ver = ds_rev or "v0"          # 버전 미지정 = main = v0(미버전)
    model_tag = f"{dataset_ver}-s{max_steps}" + ("-full" if full else "")

    env: dict[str, str] = {}
    for k in _SECRET_KEYS:
        v = os.getenv(k)
        if v:
            env[k] = v
    # flow / training params
    env["HF_DATASET_REPO"] = ds_repo
    if ds_rev:
        env["HF_DATASET_REVISION"] = ds_rev
    # Force classic downloads — the Xet backend (default in huggingface_hub >=1.x)
    # stalls fetching our many-small-file dataset in pod/headless envs; classic
    # HTTP downloads progress reliably. snapshot_download reads this at runtime.
    env["HF_HUB_DISABLE_XET"] = "1"
    if hf_output_repo:
        env["HF_OUTPUT_REPO"] = hf_output_repo
        env["HF_OUTPUT_TAG"] = model_tag
    env["MAX_STEPS"] = str(max_steps)
    env["GLOBAL_BATCH_SIZE"] = str(global_batch_size)
    env["NUM_GPUS"] = str(num_gpus)
    # W&B 키 없으면 use_wandb 끔 (키 없이 wandb.init 이 멈추거나 에러나는 것 방지).
    env["USE_WANDB"] = "true" if os.getenv("WANDB_API_KEY") else "false"
    if learning_rate is not None:
        env["LEARNING_RATE"] = str(learning_rate)
    if save_steps is not None:
        env["SAVE_STEPS"] = str(save_steps)
    # 체크포인트는 resume 용으로 유지하되 누적은 막는다 — 최신 N개만 (기본 1).
    # 3B 체크포인트가 ~29GB라 2개+ 쌓이면 볼륨이 터진다(저장 시 임시 2개 피크).
    env["SAVE_TOTAL_LIMIT"] = str(save_total_limit)
    if full:
        env["TUNE_LLM"] = "true"
        env["TUNE_VISUAL"] = "true"

    pod_id = create(
        name=name, image_name=image, gpu_id=gpu, gpu_count=num_gpus,
        volume=volume, container_disk=container_disk, cloud_type=cloud_type,
        ports=DEFAULT_PORTS, env=env,
    )
    print(f"[launch_train] pod_id = {pod_id}  (max_steps={max_steps}, full={full}, gpu={gpu.name})")

    # 런치 시점에 모델 항목을 원장에 기록(eval=null). 학습은 파드에서 비동기로 끝나므로
    # 여기선 "시도"를 남기고, 평가 후 `manifest.py set-eval` 로 eval 을 채운다.
    if hf_output_repo:
        from scripts.manifest import add_model, slug_from_repo
        add_model(
            task or slug_from_repo(ds_repo), model_tag,
            dataset=dataset_ver, steps=max_steps, full=full,
            repo=hf_output_repo, tag=model_tag, eval=None,
        )
        print(f"[launch_train] 모델 태그 = {hf_output_repo}@{model_tag}  (평가 후: "
              f"python scripts/manifest.py set-eval {task or slug_from_repo(ds_repo)} {model_tag} <값>)")

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
    p.add_argument("--hf-dataset-repo", default="adwel94/maniskill-threecubes-lerobot",
                   help="repo 또는 repo@<버전태그> (예: ...lerobot@v1) — 버전이 모델 태그에 들어감")
    p.add_argument("--hf-output-repo", default=None, help="체크포인트 업로드 대상 (미지정 시 업로드 skip)")
    p.add_argument("--task", default=None, help="MANIFEST 태스크 키 (기본: dataset repo slug)")
    p.add_argument("--max-steps", type=int, default=500)
    p.add_argument("--global-batch-size", type=int, default=16)
    p.add_argument("--learning-rate", type=float, default=None)
    p.add_argument("--save-steps", type=int, default=None)
    p.add_argument("--save-total-limit", type=int, default=1,
                   help="유지할 체크포인트 수 (기본 1=최신만; 누적 방지)")
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
        save_steps=args.save_steps, save_total_limit=args.save_total_limit,
        num_gpus=args.num_gpus, full=args.full, task=args.task,
        volume=args.volume, container_disk=args.container_disk, image=args.image,
        cloud_type=args.cloud_type)


if __name__ == "__main__":
    _cli()
