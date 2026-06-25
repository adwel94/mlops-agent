#!/usr/bin/env bash
# ① 로드 + 스모크 — "GR00T 가 우리 데이터를 읽고 2 스텝 도는가".
# bootstrap.sh 가 먼저 끝나 있어야 함.
#
# 사용:  bash smoke_test.sh [DATASET_DIR]
#   DATASET_DIR 기본 = /workspace/lerobot  (h5_to_lerobot 출력 디렉토리)
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
GR00T_DIR="${WORKSPACE}/Isaac-GR00T"
DATASET_DIR="${1:-${WORKSPACE}/lerobot}"
# 이 번들과 같은 위치의 modality config (maniskill repo 를 /workspace 에 둔 경우).
CONFIG_PATH="${CONFIG_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/new_embodiment_config.py}"
export HF_HOME="${HF_HOME:-${WORKSPACE}/hf}"
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

cd "${GR00T_DIR}"

echo "==> [1/2] stats.json / relative_stats.json 재생성 (로더가 stats.json 존재를 요구)"
uv run python scripts/repair_lerobot_metadata.py "${DATASET_DIR}" \
    --embodiment-tag new_embodiment

echo "==> [2/2] launch_finetune --max-steps 2  (로드 + forward/backward 스모크)"
uv run python -m gr00t.experiment.launch_finetune \
    --base-model-path nvidia/GR00T-N1.7-3B \
    --dataset-path "${DATASET_DIR}" \
    --embodiment-tag new_embodiment \
    --modality-config-path "${CONFIG_PATH}" \
    --max-steps 2 \
    --global-batch-size 1 \
    --num-gpus 1 \
    --output-dir "${WORKSPACE}/outputs/smoke"

echo ""
echo "==> 스모크 통과 = 데이터 로드 + 학습 경로 정상. (h5_to_lerobot 출력이 GR00T 와 정합)"
