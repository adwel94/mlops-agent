"""Launch the dataset-download probe pod (cheapest GPU, image ENTRYPOINT).

Bypasses runpod_up's mode/env logic — calls create() directly so the probe
image's own ENTRYPOINT runs and only the env it needs is injected. The probe
reports verdicts to the Discord STDOUT webhook (read via read_logs.py).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))  # project root
sys.path.insert(0, os.path.dirname(_HERE))  # cloud/runpod (runpod_client)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.env_config import load_env          # noqa: E402
from runpod_client import CloudType, GPUType, create, pod  # noqa: E402

load_env()

DATASET = os.environ.get("PROBE_DATASET", "adwel94/maniskill-threecubes-lerobot")
GPU = os.environ.get("PROBE_GPU", "NVIDIA_RTX_A4000")
CLOUD = os.environ.get("PROBE_CLOUD", "SECURE")   # COMMUNITY = more stock, cheaper

env = {"HF_DATASET": DATASET}
for k in ("HF_TOKEN", "STDOUT_WEBHOOK_URL"):
    v = os.getenv(k)
    if v:
        env[k] = v

pod_id = create(
    name="dl-probe",
    image_name="adwel94/maniskill-dl-probe:latest",
    gpu_id=GPUType[GPU],
    gpu_count=1,
    volume=10,
    container_disk=10,
    cloud_type=CloudType[CLOUD],
    ports=["22/tcp"],
    env=env,
)
print(f"[launch_probe] pod_id = {pod_id}  gpu={GPU}  cloud={CLOUD}  dataset={DATASET}")
p = pod(pod_id)
for k in ("id", "name", "desiredStatus", "costPerHr"):
    if k in p:
        print(f"  {k}: {p.get(k)}")
print(f"  종료: python cloud/runpod/runpod_down.py {pod_id} --yes")
