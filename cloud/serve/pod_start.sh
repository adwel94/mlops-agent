#!/usr/bin/env bash
# RunPod 컨테이너 ENTRYPOINT — 부팅 시 자급식 프로비저닝.
#
# 설계: 도커 이미지엔 무거운 걸 굽지 않는다(레이어 가볍게 = 빌드/푸시/콜드풀 빠름,
# 호환성은 런타임 설치로 해결). 패키지 설치·데이터셋 다운로드·서버 실행은 전부
# "컨테이너 시작 시점"인 여기서 한다. 즉 이미지엔 이 가벼운 스크립트만 COPY.
#
#   1) 베이스 ssh/jupyter 기동 (디버그 접근용, 백그라운드)
#   2) bootstrap.sh           — apt/uv/GR00T 설치 (멱등)
#   3) fetch_dataset.sh       — HF Hub 에서 LeRobot 데이터셋 받기 (HF_DATASET 지정 시)
#   4) MODE 분기              — serve(④ 정책서버) / smoke(① 스모크) / idle(대기)
#
# env: MODE, HF_DATASET, HF_TOKEN, SERVE_BASE, MODEL_PATH, DATASET_DIR (아래 스크립트로 전달)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUNBUFFERED=1   # stdout 즉시 flush → 시퍼/콘솔 지연 최소화

# 0) stdout 시퍼: 부팅 첫 줄부터 전체 출력을 RUN_LOG 로 tee 하고, 백그라운드 워커가
#    Discord STDOUT 채널로 흘린다(에이전트가 봇 토큰으로 읽음 = 원격 디버깅 인프라).
#    bootstrap 보다 먼저 시작해야 부팅/설치/모델로드 실패까지 잡힌다.
RUN_LOG="${RUN_LOG:-/workspace/run.log}"
mkdir -p "$(dirname "$RUN_LOG")" 2>/dev/null || true
exec > >(tee -a "$RUN_LOG") 2>&1
if [ -n "${STDOUT_WEBHOOK_URL:-}" ]; then
    python3 "${HERE}/_log_shipper.py" "$RUN_LOG" --interval 20 &
fi

echo "==> [pod_start] MODE=${MODE:-idle} HF_DATASET=${HF_DATASET:-<none>} HF_MODEL=${HF_MODEL:-<none>} SERVE_BASE=${SERVE_BASE:-0}"

# 파이프라인 마일스톤 — 학습 파드(train_flow)가 PIPELINE 채널에 상세 로깅하듯, serve 파드도
# 부팅·모델준비·ready·실패를 PIPELINE 에 pod_id 와 함께 남긴다. STDOUT(raw·파드간 누적)과 달리
# pod_id 로 구분돼 "이 파드가 준비됐나"를 잔상 없이 판단할 수 있다. notify 는 웹훅 없거나
# 실패해도 조용히 무시(관측≠게이트).
_POD="${RUNPOD_POD_ID:-?}"
notify() { python3 "${HERE}/notify.py" "$1" --channel pipeline || true; }

notify "🚀 *[serve] 파드 부팅* pod=\`${_POD}\` MODE=\`${MODE:-idle}\` model=\`${HF_MODEL:-<none>}@${HF_MODEL_REVISION:-main}\`"

# 1) 베이스 서비스(ssh/jupyter) — RunPod 기본 start 스크립트가 있으면 백그라운드로.
#    (디버그용. happy-path 는 SSH 불필요 — 평가 롤아웃은 5555/tcp 만 씀.)
if [ -f /start.sh ]; then
    echo "==> base services (/start.sh) in background"
    bash /start.sh &
fi

# 2) 패키지 설치 (멱등 — 재부팅/재시작에도 안전)
bash "${HERE}/bootstrap.sh"
notify "📦 *[serve] bootstrap 완료* pod=\`${_POD}\` — 의존성 설치 끝, 모델 다운로드로"

# 3) 데이터셋 — HF_DATASET 지정 시 HF Hub 에서 /workspace/lerobot 로
if [ -n "${HF_DATASET:-}" ]; then
    bash "${HERE}/fetch_dataset.sh"
fi

# 3.5) 모델 — HF_MODEL 지정 시 HF Hub 에서 체크포인트 받아 MODEL_PATH 자동 설정.
#      (serve_policy 파인튜닝 분기는 로컬 MODEL_PATH 를 요구 → HF 가 단일 출처.)
if [ -n "${HF_MODEL:-}" ]; then
    bash "${HERE}/fetch_model.sh"
    _MP_FILE="${WORKSPACE:-/workspace}/.model_path"
    if [ -f "${_MP_FILE}" ]; then
        MODEL_PATH="$(cat "${_MP_FILE}")"
        export MODEL_PATH
        echo "==> MODEL_PATH=${MODEL_PATH}"
        # 받은 revision 을 마일스톤에 박아 "의도한 태그를 받았나" 대조를 남긴다(@main 오배포 감지).
        notify "📥 *[serve] 모델 준비* pod=\`${_POD}\` \`${HF_MODEL}@${HF_MODEL_REVISION:-main}\` → \`${MODEL_PATH}\`"
    fi
fi

# 4) 모드 분기
case "${MODE:-idle}" in
    serve)
        echo "==> MODE=serve — GR00T 정책 서버 기동 (5555/tcp)"
        # exec 하지 않는다: 서버가 치명적 에러로 죽어도 컨테이너 PID1 은 살아있게 해
        # RunPod 의 자동 재시작(=restart-loop = 조용한 과금)을 막고, 디버그 접속을 남긴다.
        bash "${HERE}/serve_policy.sh" || echo "==> serve_policy 종료(에러) — 로그 확인"
        echo "==> serve 종료 — idle 로 유지 (restart-loop 방지, SSH/Jupyter 디버그 가능)"
        sleep infinity
        ;;
    smoke)
        echo "==> MODE=smoke — ① 로드+스모크"
        bash "${HERE}/smoke_test.sh" || echo "==> smoke 실패 (로그 확인) — 컨테이너는 유지"
        echo "==> smoke done — idle 로 유지 (SSH 디버그 가능)"
        sleep infinity
        ;;
    *)
        echo "==> MODE=idle — 프로비저닝 완료, 컨테이너 유지 (SSH 접속해 수동 실행 가능)"
        sleep infinity
        ;;
esac
