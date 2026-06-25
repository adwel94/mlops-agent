#!/usr/bin/env bash
# RunPod 부팅 후 환경 셋업 — 멱등(여러 번 돌려도 안전).
# RunPod 팁대로 "공식 베이스 이미지 + 컨테이너 부팅 시 설치" 패턴.
# 베이스 이미지: RunPod 공식 PyTorch/CUDA 12.8 이미지 권장 (드라이버/CUDA 내장).
#
# SSH 접속 후:  bash /workspace/maniskill/cloud/runpod/bootstrap.sh
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
GR00T_DIR="${WORKSPACE}/Isaac-GR00T"
# 모델/HF 캐시는 영속 볼륨에 (컨테이너 디스크 절약, 재부팅 후 재다운로드 방지).
export HF_HOME="${HF_HOME:-${WORKSPACE}/hf}"
mkdir -p "${HF_HOME}"

echo "==> apt deps (ffmpeg, git-lfs, python3.10-dev)"
apt-get update -y
# python3.10-dev: deepspeed→triton 이 trainer 생성 시 cuda_utils 를 런타임 JIT 컴파일하는데
#   Python.h 가 없으면 gcc 가 실패한다(venv 는 시스템 python3.10 기반). 헤더 제공 필수.
apt-get install -y ffmpeg git git-lfs python3.10-dev
git lfs install

echo "==> uv 설치"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

echo "==> Isaac-GR00T clone (shallow, no submodules)"
# 서브모듈(LIBERO/SimplerEnv/robocasa)은 GR00T eval 벤치마크용 — 서빙·우리 학습엔 불필요.
# pyproject 에 external_dependencies 경로 의존성 없음 확인됨 → 빼도 uv sync 정상.
# --depth 1 로 히스토리도 트림(클론 가속). 서빙·학습 양쪽 부팅 단축.
if [ ! -d "${GR00T_DIR}/.git" ]; then
    git clone --depth 1 https://github.com/NVIDIA/Isaac-GR00T "${GR00T_DIR}"
else
    echo "    이미 존재 — skip"
fi

echo "==> uv sync --python 3.10 (flash-attn 등 GPU 의존성 포함)"
cd "${GR00T_DIR}"
uv sync --python 3.10

echo ""
echo "==> 셋업 완료."
echo "    GR00T_DIR = ${GR00T_DIR}"
echo "    HF_HOME   = ${HF_HOME}"
echo "    다음: 데이터셋을 ${WORKSPACE}/lerobot 에 올린 뒤 smoke_test.sh 실행"
