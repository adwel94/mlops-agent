#!/usr/bin/env bash
# ④-eval (server side) — serve a GR00T policy over ZMQ so the WSL rollout client
# (scripts/gr00t_eval.py) can drive it in sim and measure success rate.
# bootstrap.sh must have run. Runs on the RunPod GPU box.
#
# 사용:
#   # 파인튜닝 체크포인트 평가 (기본):
#   MODEL_PATH=/workspace/outputs/<run>/checkpoint-XXXX  bash serve_policy.sh
#   # 베이스 모델 sanity 베이스라인 (modality config + 데이터셋 stats 필요):
#   SERVE_BASE=1 DATASET_DIR=/workspace/lerobot  bash serve_policy.sh
#
# 포트: PolicyServer 는 0.0.0.0:5555 로 listen. RunPod 콘솔에서 pod 의 5555/tcp 를
# 노출(expose)해야 외부(내 WSL)에서 접속 가능 — 노출 후 나오는 proxy host:port 를
# gr00t_eval --server-host/--server-port 에 넣는다. (또는 SSH 터널.)
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
GR00T_DIR="${GR00T_DIR:-${WORKSPACE}/Isaac-GR00T}"
PORT="${PORT:-5555}"
HOST="${HOST:-0.0.0.0}"
EMBODIMENT_TAG="${EMBODIMENT_TAG:-new_embodiment}"
CONFIG_PATH="${CONFIG_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/new_embodiment_config.py}"
export HF_HOME="${HF_HOME:-${WORKSPACE}/hf}"
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

cd "${GR00T_DIR}"

# torch 의 첫 CUDA init 이 간헐적으로 깨짐("CUDA unknown error" → devices=0, nvidia-smi 는
# 정상). torch 가 그 "0 디바이스"를 프로세스 내에 캐싱하므로 같은 프로세스 재시도는 무의미 →
# 매번 새 프로세스로 재기동한다. 정상 기동하면 서버가 블로킹(반환 X)이라 루프가 거기서 멈춰
# 대기하고, 크래시로 반환되면 다음 시도로 넘어간다.
SERVE_RETRIES="${SERVE_RETRIES:-4}"
SERVE_RETRY_SLEEP="${SERVE_RETRY_SLEEP:-10}"

if [ "${SERVE_BASE:-0}" = "1" ]; then
    # 베이스 모델: modality config 등록 + 데이터셋 stats 로 정규화.
    MODEL_PATH="${MODEL_PATH:-nvidia/GR00T-N1.7-3B}"
    DATASET_DIR="${DATASET_DIR:-${WORKSPACE}/lerobot}"
    # 로더가 stats.json 을 요구하고, action rep=RELATIVE 라 relative_stats.json 도 필요.
    # h5_to_lerobot 가 stats.json 은 쓰지만, GR00T env 기준으로 재생성해 정합 보장(멱등).
    echo "==> repair metadata (stats/relative_stats) for base serving"
    uv run python scripts/repair_lerobot_metadata.py "${DATASET_DIR}" \
        --embodiment-tag "${EMBODIMENT_TAG}" || echo "    (repair 실패 — 기존 stats 로 진행)"
    echo "==> serving BASE model ${MODEL_PATH}  (config=${CONFIG_PATH}, stats from ${DATASET_DIR})"
    SERVE_ARGS=(--model-path "${MODEL_PATH}" --embodiment-tag "${EMBODIMENT_TAG}" \
                --modality-config-path "${CONFIG_PATH}" --dataset-path "${DATASET_DIR}" \
                --host "${HOST}" --port "${PORT}")
else
    # 파인튜닝 체크포인트: modality config + stats 가 체크포인트에 포함됨.
    : "${MODEL_PATH:?set MODEL_PATH=/workspace/outputs/<run>/checkpoint-XXXX}"
    echo "==> serving FINETUNED checkpoint ${MODEL_PATH}"
    SERVE_ARGS=(--model-path "${MODEL_PATH}" --embodiment-tag "${EMBODIMENT_TAG}" \
                --host "${HOST}" --port "${PORT}")
fi

attempt=1
while [ "${attempt}" -le "${SERVE_RETRIES}" ]; do
    echo "==> serve attempt ${attempt}/${SERVE_RETRIES}"
    set +e
    uv run python gr00t/eval/run_gr00t_server.py "${SERVE_ARGS[@]}"
    rc=$?
    set -e
    [ "${rc}" -eq 0 ] && exit 0   # (정상 시 서버는 블로킹 — 여기 도달 안 함)
    echo "==> serve attempt ${attempt} 실패 (exit ${rc}) — ${SERVE_RETRY_SLEEP}s 후 재시도"
    attempt=$((attempt + 1))
    sleep "${SERVE_RETRY_SLEEP}"
done
echo "==> serve ${SERVE_RETRIES}회 모두 실패 — 포기"
exit 1
