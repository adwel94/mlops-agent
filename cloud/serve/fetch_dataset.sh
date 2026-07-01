#!/usr/bin/env bash
# HF Hub 에서 LeRobot 데이터셋을 받아 /workspace/lerobot 에 푼다 (부팅 시).
#
# 직접 전송(rsync/Jupyter) 대신 HF Hub 를 single source of truth 로 — 데이터가 커져도
# 이미지·파드와 분리되어 재현 가능(이미지 + HF repo id + 토큰만으로 자급).
#
# env:
#   HF_DATASET   (필수)  예: adwel94/maniskill-threecubes-lerobot
#   HF_TOKEN     (private repo 면 필요)  huggingface_hub 가 자동으로 읽음
#   DATASET_DIR  (선택)  기본 /workspace/lerobot
#   HF_REVISION  (선택)  브랜치/태그/커밋 (기본 main)
set -uo pipefail
WORKSPACE="${WORKSPACE:-/workspace}"
TARGET="${DATASET_DIR:-${WORKSPACE}/lerobot}"
: "${HF_DATASET:?set HF_DATASET=<org>/<repo>}"
export HF_HOME="${HF_HOME:-${WORKSPACE}/hf}"
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

echo "==> HF dataset download: ${HF_DATASET}@${HF_REVISION:-main} -> ${TARGET}"
# 가벼운 의존성 — 런타임 설치(이미지엔 안 구움). hf CLI 는 HF_TOKEN env 를 자동 인식.
pip install -q -U "huggingface_hub[cli]"
hf download "${HF_DATASET}" \
    --repo-type dataset \
    --revision "${HF_REVISION:-main}" \
    --local-dir "${TARGET}"

echo "==> dataset ready: ${TARGET}"
ls -la "${TARGET}" || true
