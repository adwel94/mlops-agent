#!/usr/bin/env bash
# RunPod 부팅 후 환경 셋업 — 멱등(여러 번 돌려도 안전).
# RunPod 팁대로 "공식 베이스 이미지 + 컨테이너 부팅 시 설치" 패턴. 이렇게 부팅 시점(=GPU 있는
# RunPod 환경)에 설치해야 flash-attn 등이 실제 GPU arch 로 컴파일된다 — 로컬 빌드+푸시는
# arch 가 어긋나 충돌(그래서 thin 이미지 유지, 무거운 설치는 굽지 않고 여기서).
# 베이스 이미지: RunPod 공식 PyTorch/CUDA 12.8 이미지 권장 (드라이버/CUDA 내장).
#
# SSH 접속 후:  bash /workspace/maniskill/cloud/common/bootstrap.sh
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
GR00T_DIR="${WORKSPACE}/Isaac-GR00T"
# 모델/HF 캐시는 영속 볼륨에 (컨테이너 디스크 절약, 재부팅 후 재다운로드 방지).
export HF_HOME="${HF_HOME:-${WORKSPACE}/hf}"
mkdir -p "${HF_HOME}"

# 부팅 계측: 단계 경계마다 epoch 스탬프 → 끝에서 BOOT_PROFILE 한 줄 emit.
# "패키지 다 설치하면" = uv sync 완료 지점. 같은 task 의 부팅 시간을 파드/머신 간 비교.
_T0=$(date +%s)

echo "==> apt deps (ffmpeg, git-lfs, python3.10-dev)"
apt-get update -y
# python3.10-dev: deepspeed→triton 이 trainer 생성 시 cuda_utils 를 런타임 JIT 컴파일하는데
#   Python.h 가 없으면 gcc 가 실패한다(venv 는 시스템 python3.10 기반). 헤더 제공 필수.
apt-get install -y ffmpeg git git-lfs python3.10-dev
git lfs install
_T_APT=$(date +%s)

echo "==> uv 설치"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

echo "==> Isaac-GR00T clone (shallow, no submodules)"
# 서브모듈(LIBERO/SimplerEnv/robocasa)은 GR00T eval 벤치마크용 — 서빙·우리 학습엔 불필요.
# pyproject 에 external_dependencies 경로 의존성 없음 확인됨 → 빼도 uv sync 정상.
# --depth 1 로 히스토리도 트림(클론 가속). 서빙·학습 양쪽 부팅 단축.
# 저속중단+타임아웃+재시도: 나쁜 호스트에서 GitHub 로의 clone 이 무한 hang 하는 걸 막는다
#   (1KB/s 미만 20초 지속 → git 이 스스로 abort; 그래도 안 끝나면 180초 timeout).
git config --global http.lowSpeedLimit 1000
git config --global http.lowSpeedTime 20
if [ ! -d "${GR00T_DIR}/.git" ]; then
    _cloned=0
    for i in 1 2 3; do
        if timeout 180 git clone --depth 1 https://github.com/NVIDIA/Isaac-GR00T "${GR00T_DIR}"; then
            _cloned=1; break
        fi
        echo "    clone 시도 ${i} 실패/타임아웃 — 정리 후 재시도"
        rm -rf "${GR00T_DIR}"
        sleep 5
    done
    [ "${_cloned}" -eq 1 ] || { echo "❌ Isaac-GR00T clone 3회 실패 — GitHub 도달 불가 호스트"; exit 1; }
else
    echo "    이미 존재 — skip"
fi
_T_CLONE=$(date +%s)

echo "==> uv sync --python 3.10 (flash-attn 등 GPU 의존성 포함)"
cd "${GR00T_DIR}"
uv sync --python 3.10
_T_UV=$(date +%s)

# ── 부팅 계측 emit (BOOT_TIMING 채널) ──────────────────────────────────────
# 한 줄·파싱 가능(key=value). 모든 시간 = 초. task=<MODE>:<slug> 로 같은 작업끼리 비교.
# set -e 에 안 걸리게 전 구간 가드(계측 실패가 부팅을 죽이지 않는다).
emit_boot_profile() {
    local d_apt=$(( _T_APT - _T0 ))
    local d_clone=$(( _T_CLONE - _T_APT ))      # uv 설치 + git clone (uv_sync 전까지)
    local d_uv=$(( _T_UV - _T_CLONE ))
    local d_total=$(( _T_UV - _T0 ))
    # slug: HF_MODEL 우선, 없으면 HF_DATASET — owner/접두/접미 정리해 task 키 일치.
    local src="${HF_MODEL:-${HF_DATASET:-}}"
    local slug
    slug="$(basename "${src}" 2>/dev/null | sed -E 's/\.git$//; s/^gr00t-//; s/^maniskill-//; s/-lerobot$//')"
    [ -z "${slug}" ] && slug="unknown"
    local task="${MODE:-idle}:${slug}"
    local gpu
    gpu="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | tr ' ' '_')"
    [ -z "${gpu}" ] && gpu="unknown"
    local pod="${RUNPOD_POD_ID:-unknown}"
    local msg="🔧 BOOT_PROFILE v=1 task=${task} pod=${pod} gpu=${gpu} apt=${d_apt} clone=${d_clone} uv_sync=${d_uv} bootstrap=${d_total} ts=${_T_UV}"
    echo "==> ${msg}"
    if [ -n "${BOOT_TIMING_WEBHOOK_URL:-}" ]; then
        curl -sf -H "Content-Type: application/json" -X POST \
            -d "{\"content\": \"${msg}\"}" "${BOOT_TIMING_WEBHOOK_URL}" >/dev/null 2>&1 || true
    fi
}
emit_boot_profile || true

echo ""
echo "==> 셋업 완료."
echo "    GR00T_DIR = ${GR00T_DIR}"
echo "    HF_HOME   = ${HF_HOME}"
echo "    다음: 데이터셋을 ${WORKSPACE}/lerobot 에 올린 뒤 smoke_test.sh 실행"
