"""GR00T 정책 서버 파드 생성 (스킬: /gr00t_serve).

④ 평가용 정책 서버를 띄우는 얇은 전용 래퍼. 서빙은 runpod_up 의 한 *모드*
(MODE=serve)일 뿐이라, 여기서는 runpod_up.run(mode="serve", ...) 에 서빙 기본값만
박아 한 줄 호출(`/gr00t_serve <hf_model>`)로 만든다. 파드는 부팅 때 스스로
bootstrap → fetch_model(HF 체크포인트 다운로드, 체크포인트 제외 = 최종 모델만) →
serve_policy(5555/tcp) 를 자급 실행한다 (SSH 불필요).

검증 끝난 흐름: HF_MODEL=<repo> → fetch_model.sh 가 루트 가중치를 받아 MODEL_PATH 자동
설정 → serve_policy.sh 파인튜닝 분기가 그 경로로 서버 기동. 24GB(A5000)면 3B 로드 OK.

사전: export RUNPOD_API_KEY=... (+ private repo 면 HF_TOKEN)
  - Python:  from serve_up import run; run("adwel94/gr00t-threecubes-ft")
  - CLI:     python cloud/serve/serve_up.py adwel94/gr00t-threecubes-ft
"""
from __future__ import annotations

import os
import sys

# Windows 콘솔(cp949)이 em-dash 등 유니코드를 못 뱉어 출력이 깨지는 것 방지.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))          # cloud/serve
_ROOT = os.path.dirname(os.path.dirname(_HERE))             # project root
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "cloud", "runpod"))  # RunPod 원자(runpod_client/runpod_up)
from runpod_client import CloudType, GPUType  # noqa: E402
from runpod_up import DEFAULT_IMAGE, run as _up  # noqa: E402

# 서빙 기본값 — L40S(48GB) 라인이 기본. A5000/커뮤니티 풀은 부팅 stall·불량 인스턴스가
# 잦아(40분 stall, CUDA unknown error 사례) 신뢰 못함 → L40S 가 검증된 안정 라인.
DEFAULT_GPU = GPUType.NVIDIA_L40S          # 48GB
DEFAULT_VOLUME_GB = 40                     # HF 모델(~12GB) + 캐시
DEFAULT_DISK_GB = 40
# 8888=jupyter(디버그), 22=ssh(디버그), 5555=정책 서버(평가 롤아웃이 쓰는 단 하나).
DEFAULT_PORTS = ["8888/http", "22/tcp", "5555/tcp"]


def run(
    hf_model: str,
    name: str = "gr00t-serve",
    gpu: GPUType | str = DEFAULT_GPU,
    hf_model_subdir: str | None = None,
    hf_model_revision: str | None = None,
    volume: int = DEFAULT_VOLUME_GB,
    container_disk: int = DEFAULT_DISK_GB,
    image: str = DEFAULT_IMAGE,
    cloud_type: CloudType | str = CloudType.COMMUNITY,
    ports: list[str] | None = None,
) -> str:
    """정책 서버 파드를 생성하고 pod_id 반환.

    hf_model: 서빙할 파인튜닝 모델 HF repo id (필수). 부팅 때 받아 MODEL_PATH 자동 설정.
    hf_model_subdir: repo 내 체크포인트 서브폴더 (구 레이아웃 호환; 보통 불필요).
    hf_model_revision: HF repo 의 브랜치/태그/커밋 (기본 main). 같은 repo 안의 특정 버전
      태그(예: v2-s3000)를 서빙할 때 필수 — 생략 시 main(=최신 push)이 받힌다.
    """
    pod_id = _up(
        name=name, gpu=gpu, volume=volume, container_disk=container_disk,
        image=image, cloud_type=cloud_type, ports=ports or DEFAULT_PORTS,
        mode="serve", hf_model=hf_model, hf_model_subdir=hf_model_subdir,
        hf_model_revision=hf_model_revision,
    )
    print(
        "\n[gr00t_serve] 서빙 파드 부팅 중 — 5555/tcp 가 뜨면 (RunPod 콘솔/`/runpod_ls` 에서\n"
        "  publicIp + 매핑포트 확인) 이 PC WSL 에서 평가 롤아웃:\n"
        "      python scripts/gr00t_eval.py --task <task> --traj-path <소스 rgb h5> \\\n"
        "          --server-host <publicIp> --server-port <매핑포트> --instruction \"...\"\n"
        f"  종료(과금 차단):  /runpod_down {pod_id}"
    )
    return pod_id


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("hf_model", help="서빙할 파인튜닝 모델 HF repo id (예: adwel94/gr00t-threecubes-ft)")
    p.add_argument("--name", default="gr00t-serve")
    p.add_argument("--gpu", default=DEFAULT_GPU.name,
                   help="GPUType 이름 (기본 NVIDIA_L40S=48GB)")
    p.add_argument("--hf-model-subdir", default=None,
                   help="repo 내 체크포인트 서브폴더 (구 레이아웃 호환; 보통 불필요)")
    p.add_argument("--revision", dest="hf_model_revision", default=None,
                   help="HF repo 의 브랜치/태그/커밋 (기본 main) 예: v2-s3000")
    p.add_argument("--volume", type=int, default=DEFAULT_VOLUME_GB)
    p.add_argument("--container-disk", type=int, default=DEFAULT_DISK_GB)
    p.add_argument("--image", default=DEFAULT_IMAGE)
    p.add_argument("--cloud-type", default=CloudType.COMMUNITY.name,
                   choices=[c.name for c in CloudType])
    args = p.parse_args()
    run(hf_model=args.hf_model, name=args.name, gpu=args.gpu,
        hf_model_subdir=args.hf_model_subdir, hf_model_revision=args.hf_model_revision,
        volume=args.volume, container_disk=args.container_disk, image=args.image,
        cloud_type=args.cloud_type)


if __name__ == "__main__":
    _cli()
