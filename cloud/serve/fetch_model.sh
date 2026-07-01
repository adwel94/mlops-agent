#!/usr/bin/env bash
# HF Hub 에서 파인튜닝 체크포인트를 받아 로컬에 푼다 (부팅 시).
#
# serve_policy.sh 의 파인튜닝 분기는 로컬 경로(MODEL_PATH)를 요구한다. 체크포인트를
# 직접 전송하지 않고 HF Hub 를 single source of truth 로 두고 부팅 때 내려받는다
# (이미지 + repo id + 토큰만으로 자급 — fetch_dataset.sh 와 같은 패턴).
#
# env:
#   HF_MODEL          (필수)  예: adwel94/gr00t-threecubes-ft
#   HF_MODEL_SUBDIR   (선택)  repo 내 체크포인트 서브폴더 예: gr00t-ft-2a8zwjb894k3dx
#   HF_TOKEN          (private repo 면 필요)  huggingface_hub 가 자동 인식
#   MODEL_DIR         (선택)  다운로드 루트 (기본 /workspace/model)
#   HF_MODEL_REVISION (선택)  브랜치/태그/커밋 (기본 main)
# 결과: 받은 모델 경로를 ${WORKSPACE}/.model_path 에 기록 (pod_start.sh 가 읽어 MODEL_PATH 설정).
set -uo pipefail
WORKSPACE="${WORKSPACE:-/workspace}"
DEST="${MODEL_DIR:-${WORKSPACE}/model}"
: "${HF_MODEL:?set HF_MODEL=<org>/<repo>}"
export HF_HOME="${HF_HOME:-${WORKSPACE}/hf}"
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

# 가벼운 의존성 — 런타임 설치(이미지엔 안 구움). hf CLI 는 HF_TOKEN env 를 자동 인식.
pip install -q -U "huggingface_hub[cli]"

# 체크포인트(재시도 전용)는 받지 않는다 — 서빙엔 최종 모델만 필요.
#   추가로, run-root 샤드와 checkpoint-* 샤드가 동일 blob 이면 hf download 가
#   --local-dir 로 한쪽만 materialize 해 root 가중치가 누락되는 충돌이 있다 →
#   체크포인트를 제외하면 충돌이 사라져 root 가중치가 정상적으로 깔린다.
CKPT_EXCLUDE='*checkpoint-*/*'
if [ -n "${HF_MODEL_SUBDIR:-}" ]; then
    echo "==> HF model download: ${HF_MODEL}#${HF_MODEL_SUBDIR}@${HF_MODEL_REVISION:-main} -> ${DEST} (체크포인트 제외)"
    hf download "${HF_MODEL}" \
        --revision "${HF_MODEL_REVISION:-main}" \
        --include "${HF_MODEL_SUBDIR}/*" \
        --exclude "${CKPT_EXCLUDE}" \
        --local-dir "${DEST}"
    RESOLVED="${DEST}/${HF_MODEL_SUBDIR}"
else
    echo "==> HF model download: ${HF_MODEL}@${HF_MODEL_REVISION:-main} -> ${DEST} (체크포인트 제외)"
    hf download "${HF_MODEL}" \
        --revision "${HF_MODEL_REVISION:-main}" \
        --exclude "${CKPT_EXCLUDE}" \
        --local-dir "${DEST}"
    RESOLVED="${DEST}"
fi

echo "${RESOLVED}" > "${WORKSPACE}/.model_path"
echo "==> model ready: ${RESOLVED}"
ls -la "${RESOLVED}" || true
