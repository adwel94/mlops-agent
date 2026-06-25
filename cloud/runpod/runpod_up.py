"""RunPod GPU pod 생성 (스킬: /runpod_up).

runpod_client.create 위의 얇은 래퍼. dockerStartCmd 는 건드리지 않아(베이스 이미지의
jupyter/ssh 유지) SSH 접속 후 bootstrap.sh → smoke_test.sh / serve_policy.sh 를 수동
실행하는 흐름. RunPod 팁("부팅 시 설치")과 정합 — 패키지는 컨테이너 안에서 설치.

기본 포트에 5555/tcp 포함 → ④ 평가용 정책 서버(serve_policy.sh)를 바로 노출 가능.

사전: export RUNPOD_API_KEY=...
  - Python:  from runpod_up import run; run(name="gr00t-smoke")
  - CLI:     python cloud/runpod/runpod_up.py --name gr00t-smoke --gpu NVIDIA_L40S
"""
from __future__ import annotations

import os
import sys

# Windows 콘솔(cp949)이 em-dash 등 유니코드를 못 뱉어 출력이 깨지는 것 방지.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root (scripts.*)
sys.path.insert(0, _HERE)
from scripts.env_config import load_env  # noqa: E402
from runpod_client import CloudType, GPUType, create, pod  # noqa: E402

load_env()  # .env -> RUNPOD_API_KEY

# 스모크(--max-steps 2)는 3B 로드 + optimizer 라 24GB 로는 빠듯 → 48GB 권장.
# 본 파인튜닝은 A100 80GB 급 권장.
DEFAULT_GPU = GPUType.NVIDIA_L40S          # 48GB
DEFAULT_VOLUME_GB = 60                     # /workspace: HF 모델(~6GB)+데이터셋+outputs
DEFAULT_DISK_GB = 40                       # uv .venv(torch+flash-attn) 가 큼
# thin 커스텀 이미지 (프로젝트 Dockerfile: 베이스 + /app 에 cloud/runpod 스크립트).
# 베이스만 쓰려면 --image runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04
DEFAULT_IMAGE = "adwel94/maniskill-gr00t:latest"
# 8888=jupyter, 22=ssh, 5555=GR00T 정책 서버(④ 평가).
DEFAULT_PORTS = ["8888/http", "22/tcp", "5555/tcp"]


def _summary(p: dict) -> str:
    keys = ("id", "name", "desiredStatus", "costPerHr")
    return "\n".join(f"  {k}: {p.get(k)}" for k in keys if k in p)


def _build_env(
    mode: str,
    hf_dataset: str | None,
    serve_base: bool,
    model_path: str | None,
    hf_model: str | None = None,
    hf_model_subdir: str | None = None,
) -> dict[str, str]:
    """파드 ENTRYPOINT(pod_start.sh)로 넘길 env. 비밀(HF_TOKEN)은 .env 에서 끌어온다."""
    env: dict[str, str] = {"MODE": mode}
    if hf_dataset:
        env["HF_DATASET"] = hf_dataset
    if serve_base:
        env["SERVE_BASE"] = "1"
    if model_path:
        env["MODEL_PATH"] = model_path
    # HF 체크포인트(부팅 때 받아 MODEL_PATH 자동 설정). model_path(로컬)와 택일.
    if hf_model:
        env["HF_MODEL"] = hf_model
    if hf_model_subdir:
        env["HF_MODEL_SUBDIR"] = hf_model_subdir
    # 비밀: 셸/.env 에 있으면 전달.
    #   HF_TOKEN           — private HF repo·gated 모델 다운로드
    #   STDOUT_WEBHOOK_URL — stdout 시퍼가 Discord STDOUT 채널로 로그 전송(원격 디버깅)
    for k in ("HF_TOKEN", "STDOUT_WEBHOOK_URL"):
        v = os.getenv(k)
        if v:
            env[k] = v
    return env


def run(
    name: str = "gr00t",
    gpu: GPUType | str = DEFAULT_GPU,
    gpu_count: int = 1,
    volume: int = DEFAULT_VOLUME_GB,
    container_disk: int = DEFAULT_DISK_GB,
    image: str = DEFAULT_IMAGE,
    cloud_type: CloudType | str = CloudType.COMMUNITY,
    ports: list[str] | None = None,
    mode: str = "idle",
    hf_dataset: str | None = None,
    serve_base: bool = False,
    model_path: str | None = None,
    hf_model: str | None = None,
    hf_model_subdir: str | None = None,
) -> str:
    """Pod 을 생성하고 pod_id 를 반환 (+ connect 정보·다음 단계 출력).

    mode: 파드 부팅 동작 — serve(④ 정책서버) / smoke(① 스모크) / idle(대기).
    hf_dataset: HF Hub LeRobot 데이터셋 repo id (부팅 때 /workspace/lerobot 로 받음).
    serve_base: True 면 베이스 모델 서빙(SERVE_BASE=1); False+model_path 면 체크포인트.
    """
    if isinstance(gpu, str):
        gpu = GPUType[gpu]
    if isinstance(cloud_type, str):
        cloud_type = CloudType[cloud_type]
    env = _build_env(mode, hf_dataset, serve_base, model_path, hf_model, hf_model_subdir)
    pod_id = create(
        name=name, image_name=image, gpu_id=gpu, gpu_count=gpu_count,
        volume=volume, container_disk=container_disk, cloud_type=cloud_type,
        ports=ports or DEFAULT_PORTS, env=env,
    )
    print(f"[runpod_up] pod_id = {pod_id}  (MODE={mode}, HF_DATASET={hf_dataset or '<none>'})")
    print(_summary(pod(pod_id)))
    print(
        "\n파드가 부팅 때 스스로: bootstrap → HF 데이터셋 → MODE 실행 (SSH 불필요).\n"
        "  - 연결 정보(IP·포트)는 잠시 후 RunPod 콘솔 또는 /runpod_ls 에서 확인\n"
        "  - MODE=serve: 5555/tcp 가 뜨면 이 PC WSL 에서\n"
        "      python scripts/gr00t_eval.py --traj-path <소스 h5> "
        "--server-host <IP> --server-port <매핑포트> ...\n"
        "  - 진행/로그는 SSH 또는 Jupyter 로 확인 (디버그용)\n"
        f"  종료:  /runpod_down {pod_id}   (또는 python cloud/runpod/runpod_down.py {pod_id} --yes)"
    )
    return pod_id


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--name", default="gr00t")
    p.add_argument("--gpu", default=DEFAULT_GPU.name,
                   help="GPUType enum 이름 (예: NVIDIA_L40S, NVIDIA_A100_80GB_PCIE)")
    p.add_argument("--gpu-count", type=int, default=1)
    p.add_argument("--volume", type=int, default=DEFAULT_VOLUME_GB,
                   help="/workspace 영속 볼륨 GB")
    p.add_argument("--container-disk", type=int, default=DEFAULT_DISK_GB)
    p.add_argument("--image", default=DEFAULT_IMAGE)
    p.add_argument("--cloud-type", default=CloudType.COMMUNITY.name,
                   choices=[c.name for c in CloudType])
    p.add_argument("--port", action="append", dest="ports", default=None,
                   help="반복 지정 가능 (기본: 8888/http 22/tcp 5555/tcp)")
    p.add_argument("--mode", default="idle", choices=["idle", "serve", "smoke"],
                   help="부팅 동작: serve(④ 정책서버)/smoke(① 스모크)/idle(대기)")
    p.add_argument("--hf-dataset", default=None,
                   help="HF Hub LeRobot 데이터셋 repo id (부팅 때 /workspace/lerobot 로 받음)")
    p.add_argument("--serve-base", action="store_true",
                   help="베이스 모델 서빙(SERVE_BASE=1). 미지정+--model-path 면 체크포인트.")
    p.add_argument("--model-path", default=None,
                   help="로컬 체크포인트 경로 (예: /workspace/outputs/<run>/checkpoint-XXXX)")
    p.add_argument("--hf-model", default=None,
                   help="HF 체크포인트 repo id (부팅 때 받아 MODEL_PATH 자동 설정) 예: adwel94/gr00t-threecubes-ft")
    p.add_argument("--hf-model-subdir", default=None,
                   help="repo 내 체크포인트 서브폴더 예: gr00t-ft-2a8zwjb894k3dx")
    args = p.parse_args()
    run(name=args.name, gpu=args.gpu, gpu_count=args.gpu_count, volume=args.volume,
        container_disk=args.container_disk, image=args.image,
        cloud_type=args.cloud_type, ports=args.ports, mode=args.mode,
        hf_dataset=args.hf_dataset, serve_base=args.serve_base, model_path=args.model_path,
        hf_model=args.hf_model, hf_model_subdir=args.hf_model_subdir)


if __name__ == "__main__":
    _cli()
