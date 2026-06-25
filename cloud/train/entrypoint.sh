#!/usr/bin/env bash
# 학습 파드 ENTRYPOINT — 부팅 시 자급식.
#   1) 베이스 ssh/jupyter (디버그)  2) bootstrap(GR00T uv venv)
#   3) orchestration 의존성은 시스템 python 에 (gr00t venv 와 분리 — 충돌 회피)
#   4) Prefect Cloud 연결  5) train_flow.py 실행 (끝나면 flow 가 self_terminate)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
export PYTHONUNBUFFERED=1   # stdout 즉시 flush → 시퍼/콘솔 지연 최소화

# 0) stdout 시퍼: 부팅 첫 줄부터 전체 출력을 RUN_LOG 로 tee 하고, 백그라운드 워커가
#    Discord STDOUT 채널로 흘린다(에이전트가 봇 토큰으로 읽음). bootstrap 보다 먼저
#    시작해야 부팅/설치 실패까지 잡힌다. STDOUT_WEBHOOK_URL 없으면 tee 만(로컬 보존).
RUN_LOG="${RUN_LOG:-/workspace/run.log}"
mkdir -p "$(dirname "$RUN_LOG")" 2>/dev/null || true
exec > >(tee -a "$RUN_LOG") 2>&1
if [ -n "${STDOUT_WEBHOOK_URL:-}" ]; then
    python3 "${HERE}/_log_shipper.py" "$RUN_LOG" --interval 20 &
fi

echo "==> [entrypoint] GR00T 학습 파이프라인 시작"

# 1) 베이스 서비스 (디버그용)
if [ -f /start.sh ]; then bash /start.sh & fi

# 2) GR00T 설치 (uv venv) — 학습 서브프로세스가 사용
if ! bash "${HERE}/bootstrap.sh"; then
    echo "==> bootstrap 실패 — idle 유지(디버그)"; sleep infinity
fi

# 3) orchestration deps → 시스템 python (prefect 가 gr00t venv 를 오염 안 시키게)
pip install -q prefect wandb pydantic requests "huggingface_hub[cli]" || true
# 콜백(utils.discord)이 requests 를 쓰므로 gr00t venv 에도 보장
( cd /workspace/Isaac-GR00T && uv pip install -q requests ) || true

# 4) Prefect Cloud 연결 (키 있을 때)
if [ -n "${PREFECT_API_URL:-}" ]; then
    prefect config set PREFECT_API_URL="${PREFECT_API_URL}" || true
    [ -n "${PREFECT_API_KEY:-}" ] && prefect config set PREFECT_API_KEY="${PREFECT_API_KEY}" || true
fi

# 5) flow 실행 (gr00t venv 의 uv run 은 train 태스크가 서브프로세스로 호출)
cd /workspace/Isaac-GR00T
python "${HERE}/train_flow.py"
echo "==> train_flow 종료(exit=$?). self_terminate 가 파드를 지웠어야 함."

# 안전망: self_terminate 가 실패했을 때 restart-loop 대신 idle 로 유지
sleep infinity
