"""RunPod REST API 클라이언트.

serverless-mlops 패턴 기반. RunPod SDK 대신 REST API를 직접 호출하여
dockerStartCmd, 데이터센터 가용성 배치 등 payload 전체를 제어한다.
"""

import os
from enum import Enum

import requests


# ---------------------------------------------------------------------------
# 요청 타임아웃 (초). 네트워크/RunPod 지연 시 무한 블록 방지.
# ---------------------------------------------------------------------------

_TIMEOUT_READ = 30      # 조회/삭제
_TIMEOUT_CREATE = 60    # pod 생성 (스케줄링이 더 오래 걸림)


# ---------------------------------------------------------------------------
# GPUType enum + RUNPOD_GPU_MAP  (serverless-mlops config/gpu.py 동일)
# ---------------------------------------------------------------------------

class GPUType(Enum):
    NVIDIA_GEFORCE_RTX_4090 = "NVIDIA_GeForce_RTX_4090"
    NVIDIA_A40 = "NVIDIA_A40"
    NVIDIA_RTX_A5000 = "NVIDIA_RTX_A5000"
    NVIDIA_GEFORCE_RTX_3090 = "NVIDIA_GeForce_RTX_3090"
    NVIDIA_RTX_A4500 = "NVIDIA_RTX_A4500"
    NVIDIA_RTX_A6000 = "NVIDIA_RTX_A6000"
    NVIDIA_L40S = "NVIDIA_L40S"
    NVIDIA_L4 = "NVIDIA_L4"
    NVIDIA_H100_80GB_HBM3 = "NVIDIA_H100_80GB_HBM3"
    NVIDIA_RTX_4000_ADA_GENERATION = "NVIDIA_RTX_4000_Ada_Generation"
    NVIDIA_A100_80GB_PCIE = "NVIDIA_A100_80GB_PCIe"
    NVIDIA_A100_SXM4_80GB = "NVIDIA_A100-SXM4-80GB"
    NVIDIA_RTX_A4000 = "NVIDIA_RTX_A4000"
    NVIDIA_RTX_6000_ADA_GENERATION = "NVIDIA_RTX_6000_Ada_Generation"
    NVIDIA_RTX_2000_ADA_GENERATION = "NVIDIA_RTX_2000_Ada_Generation"
    NVIDIA_H200 = "NVIDIA_H200"
    NVIDIA_L40 = "NVIDIA_L40"
    NVIDIA_H100_NVL = "NVIDIA_H100_NVL"
    NVIDIA_H100_PCIE = "NVIDIA_H100_PCIe"
    NVIDIA_GEFORCE_RTX_3080_TI = "NVIDIA_GeForce_RTX_3080_Ti"
    NVIDIA_GEFORCE_RTX_3080 = "NVIDIA_GeForce_RTX_3080"
    NVIDIA_GEFORCE_RTX_3070 = "NVIDIA_GeForce_RTX_3070"
    TESLA_V100_PCIE_16GB = "Tesla_V100-PCIE-16GB"
    AMD_INSTINCT_MI300X_OAM = "AMD_Instinct_MI300X_OAM"
    NVIDIA_RTX_A2000 = "NVIDIA_RTX_A2000"
    TESLA_V100_FHHL_16GB = "Tesla_V100-FHHL-16GB"
    NVIDIA_GEFORCE_RTX_4080_SUPER = "NVIDIA_GeForce_RTX_4080_SUPER"
    TESLA_V100_SXM2_16GB = "Tesla_V100-SXM2-16GB"
    NVIDIA_GEFORCE_RTX_4070_TI = "NVIDIA_GeForce_RTX_4070_Ti"
    TESLA_V100_SXM2_32GB = "Tesla_V100-SXM2-32GB"
    NVIDIA_RTX_4000_SFF_ADA_GENERATION = "NVIDIA_RTX_4000_SFF_Ada_Generation"
    NVIDIA_RTX_5000_ADA_GENERATION = "NVIDIA_RTX_5000_Ada_Generation"
    NVIDIA_GEFORCE_RTX_5090 = "NVIDIA_GeForce_RTX_5090"
    NVIDIA_A30 = "NVIDIA_A30"
    NVIDIA_GEFORCE_RTX_4080 = "NVIDIA_GeForce_RTX_4080"
    NVIDIA_GEFORCE_RTX_5080 = "NVIDIA_GeForce_RTX_5080"
    NVIDIA_GEFORCE_RTX_3090_TI = "NVIDIA_GeForce_RTX_3090_Ti"
    NVIDIA_B200 = "NVIDIA_B200"


RUNPOD_GPU_MAP = {
    GPUType.NVIDIA_GEFORCE_RTX_4090: "NVIDIA GeForce RTX 4090",
    GPUType.NVIDIA_A40: "NVIDIA A40",
    GPUType.NVIDIA_RTX_A5000: "NVIDIA RTX A5000",
    GPUType.NVIDIA_GEFORCE_RTX_3090: "NVIDIA GeForce RTX 3090",
    GPUType.NVIDIA_RTX_A4500: "NVIDIA RTX A4500",
    GPUType.NVIDIA_RTX_A6000: "NVIDIA RTX A6000",
    GPUType.NVIDIA_L40S: "NVIDIA L40S",
    GPUType.NVIDIA_L4: "NVIDIA L4",
    GPUType.NVIDIA_H100_80GB_HBM3: "NVIDIA H100 80GB HBM3",
    GPUType.NVIDIA_RTX_4000_ADA_GENERATION: "NVIDIA RTX 4000 Ada Generation",
    GPUType.NVIDIA_A100_80GB_PCIE: "NVIDIA A100 80GB PCIe",
    GPUType.NVIDIA_A100_SXM4_80GB: "NVIDIA A100-SXM4-80GB",
    GPUType.NVIDIA_RTX_A4000: "NVIDIA RTX A4000",
    GPUType.NVIDIA_RTX_6000_ADA_GENERATION: "NVIDIA RTX 6000 Ada Generation",
    GPUType.NVIDIA_RTX_2000_ADA_GENERATION: "NVIDIA RTX 2000 Ada Generation",
    GPUType.NVIDIA_H200: "NVIDIA H200",
    GPUType.NVIDIA_L40: "NVIDIA L40",
    GPUType.NVIDIA_H100_NVL: "NVIDIA H100 NVL",
    GPUType.NVIDIA_H100_PCIE: "NVIDIA H100 PCIe",
    GPUType.NVIDIA_GEFORCE_RTX_3080_TI: "NVIDIA GeForce RTX 3080 Ti",
    GPUType.NVIDIA_GEFORCE_RTX_3080: "NVIDIA GeForce RTX 3080",
    GPUType.NVIDIA_GEFORCE_RTX_3070: "NVIDIA GeForce RTX 3070",
    GPUType.TESLA_V100_PCIE_16GB: "Tesla V100-PCIE-16GB",
    GPUType.AMD_INSTINCT_MI300X_OAM: "AMD Instinct MI300X OAM",
    GPUType.NVIDIA_RTX_A2000: "NVIDIA RTX A2000",
    GPUType.TESLA_V100_FHHL_16GB: "Tesla V100-FHHL-16GB",
    GPUType.NVIDIA_GEFORCE_RTX_4080_SUPER: "NVIDIA GeForce RTX 4080 SUPER",
    GPUType.TESLA_V100_SXM2_16GB: "Tesla V100-SXM2-16GB",
    GPUType.NVIDIA_GEFORCE_RTX_4070_TI: "NVIDIA GeForce RTX 4070 Ti",
    GPUType.TESLA_V100_SXM2_32GB: "Tesla V100-SXM2-32GB",
    GPUType.NVIDIA_RTX_4000_SFF_ADA_GENERATION: "NVIDIA RTX 4000 SFF Ada Generation",
    GPUType.NVIDIA_RTX_5000_ADA_GENERATION: "NVIDIA RTX 5000 Ada Generation",
    GPUType.NVIDIA_GEFORCE_RTX_5090: "NVIDIA GeForce RTX 5090",
    GPUType.NVIDIA_A30: "NVIDIA A30",
    GPUType.NVIDIA_GEFORCE_RTX_4080: "NVIDIA GeForce RTX 4080",
    GPUType.NVIDIA_GEFORCE_RTX_5080: "NVIDIA GeForce RTX 5080",
    GPUType.NVIDIA_GEFORCE_RTX_3090_TI: "NVIDIA GeForce RTX 3090 Ti",
    GPUType.NVIDIA_B200: "NVIDIA B200",
}


class CloudType(Enum):
    SECURE = "SECURE"
    COMMUNITY = "COMMUNITY"


# ---------------------------------------------------------------------------
# REST API 기본 설정
# ---------------------------------------------------------------------------

_BASE_URL = "https://rest.runpod.io/v1/pods"


def _headers() -> dict:
    token = os.getenv("RUNPOD_API_KEY")
    if not token:
        raise RuntimeError(
            "RUNPOD_API_KEY 환경변수가 설정되지 않았습니다. "
            "RunPod 콘솔에서 발급한 API 키를 export 하세요."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# REST API 함수 4개  (serverless-mlops cloud/runpod/runpod_client.py 동일)
# ---------------------------------------------------------------------------

def create(
    name: str,
    env: dict[str, str] | None = None,
    gpu_id: GPUType = GPUType.NVIDIA_GEFORCE_RTX_4090,
    gpu_count: int = 1,
    volume: int = 50,
    container_disk: int = 30,
    image_name: str = "",
    start_command: list[str] | None = None,
    ports: list[str] | None = None,
    template_id: str = "",
    cloud_type: CloudType = CloudType.COMMUNITY,
) -> str:
    """Pod을 생성하고 pod_id를 반환한다.

    26개 데이터센터 가용성 우선 배치, dockerStartCmd 지원.
    template_id가 주어지면 RunPod 템플릿 기반으로 생성한다.

    container_disk: 컨테이너 디스크 크기(GB). 모델 빌드 캐시·체크포인트가
        클 경우 기본 30을 올린다. 영속 데이터는 volume(/workspace)에 둔다.
    """
    env = env or {}
    start_command = start_command or []
    ports = ports or ["8888/http", "22/tcp"]

    payload = {
        "cloudType": cloud_type.value,
        "computeType": "GPU",
        "containerDiskInGb": container_disk,
        "cpuFlavorPriority": "availability",
        "dataCenterIds": [
            "EU-RO-1", "CA-MTL-1", "EU-SE-1", "US-IL-1", "EUR-IS-1",
            "EU-CZ-1", "US-TX-3", "EUR-IS-2", "US-KS-2", "US-GA-2",
            "US-WA-1", "US-TX-1", "CA-MTL-3", "EU-NL-1", "US-TX-4",
            "US-CA-2", "US-NC-1", "OC-AU-1", "US-DE-1", "EUR-IS-3",
            "CA-MTL-2", "AP-JP-1", "EUR-NO-1", "EU-FR-1", "US-KS-3",
            "US-GA-1",
        ],
        "dataCenterPriority": "availability",
        "env": env,
        "globalNetworking": False,
        "gpuTypeIds": [RUNPOD_GPU_MAP[gpu_id]],
        "gpuCount": gpu_count,
        "gpuTypePriority": "availability",
        # 이미지 베이스가 cuda12.8 → 호스트 드라이버가 CUDA 12.8+ 를 지원해야 컨테이너가
        # 뜬다. 이 필터가 없으면 낡은 드라이버 호스트에 배치돼 nvidia-container-cli 가
        # 'cuda>=12.8' 불만족으로 기동을 거부한다(컨테이너 시작 실패 → IP/runtime 안 뜸).
        "allowedCudaVersions": ["12.8", "12.9"],
        "interruptible": False,
        "locked": False,
        "name": name,
        "ports": ports,
        "vcpuCount": 2,
        "volumeInGb": volume,
        "volumeMountPath": "/workspace",
    }

    if template_id:
        payload["templateId"] = template_id
    if image_name:
        payload["imageName"] = image_name
    if start_command:
        payload["dockerStartCmd"] = start_command

    response = requests.post(
        _BASE_URL, json=payload, headers=_headers(), timeout=_TIMEOUT_CREATE
    )

    if not response.ok:
        print(f"RunPod API Create Error (Status: {response.status_code})")
        print(f"Response Body: {response.text}")
        response.raise_for_status()

    data = response.json()
    if "id" not in data:
        print(f"Unexpected API Response (Missing 'id'): {data}")
        raise KeyError(f"RunPod API did not return a pod ID. Response: {data}")

    return data["id"]


def delete(pod_id: str) -> str:
    """Pod을 삭제한다."""
    response = requests.delete(
        f"{_BASE_URL}/{pod_id}", headers=_headers(), timeout=_TIMEOUT_READ
    )
    if not response.ok:
        print(f"RunPod API Delete Error (Status: {response.status_code}, Pod: {pod_id})")
        print(f"Response Body: {response.text}")
        response.raise_for_status()
    return response.text


def pods() -> list[dict]:
    """전체 Pod 목록을 반환한다."""
    response = requests.get(_BASE_URL, headers=_headers(), timeout=_TIMEOUT_READ)
    if not response.ok:
        print(f"RunPod API List Error (Status: {response.status_code})")
        print(f"Response Body: {response.text}")
        response.raise_for_status()
    return response.json()


def pod(pod_id: str) -> dict:
    """특정 Pod의 상세 정보를 반환한다."""
    response = requests.get(
        f"{_BASE_URL}/{pod_id}", headers=_headers(), timeout=_TIMEOUT_READ
    )
    if not response.ok:
        print(f"RunPod API Get Error (Status: {response.status_code}, Pod: {pod_id})")
        print(f"Response Body: {response.text}")
        response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# 템플릿 기반 헬퍼
# ---------------------------------------------------------------------------

def create_from_template(
    name: str,
    template_id: str,
    gpu_id: GPUType = GPUType.NVIDIA_GEFORCE_RTX_4090,
    gpu_count: int = 1,
    volume: int = 50,
    container_disk: int = 30,
) -> str:
    """RunPod 템플릿 기반으로 Pod을 생성한다."""
    return create(
        name=name,
        gpu_id=gpu_id,
        gpu_count=gpu_count,
        volume=volume,
        container_disk=container_disk,
        template_id=template_id,
    )
