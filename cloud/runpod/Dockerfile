# serve 이미지 (GR00T 정책 서버) — Thin: RunPod 공식 베이스 + 가벼운 cloud/runpod 스크립트만.
#
# 설계(= RunPod 팁): 무거운 의존성(GR00T clone + uv sync: torch/flash-attn)도 apt 패키지도
# 이미지에 RUN 으로 굽지 않는다 — flash-attn 은 빌드 시점에 감지한 GPU arch 로 컴파일되는데,
# 로컬 빌드엔 GPU 가 없어 arch 가 어긋나 런타임 충돌(경험상 잦음). 대신 가벼운 스크립트만 COPY
# 하고, 설치·데이터셋/모델 다운로드·서버 실행은 전부 ENTRYPOINT(pod_start.sh = GPU 있는 RunPod
# 부팅 시점)에서 한다 → 이미지 레이어는 수십 KB, 빌드 즉시, arch 정확.
#
# 빌드/푸시 (프로젝트 루트에서, -f 로 이 파일 지정):
#   docker build -f cloud/runpod/Dockerfile -t adwel94/maniskill-gr00t:0.3 -t adwel94/maniskill-gr00t:latest .
#   docker push adwel94/maniskill-gr00t:0.3 && docker push adwel94/maniskill-gr00t:latest
# 사용: /runpod_up (env MODE/HF_DATASET 전달) → 파드가 부팅 때 스스로 설치·서빙 (SSH 불필요).

FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

WORKDIR /app

# cloud/runpod 스크립트만 COPY (pod_start/bootstrap/fetch_dataset/fetch_model/smoke_test/serve_policy.sh
# + new_embodiment_config.py + utils + _log_shipper). /workspace 는 RunPod 영속 볼륨 마운트라
# 거기 구우면 부팅 때 덮어써짐 → /app 사용. 데이터셋/모델은 굽지 않고 부팅 때 HF Hub 에서 받음.
COPY cloud/runpod/ /app/

# ENTRYPOINT = 부팅 시 자급식 프로비저닝 (설치 → 데이터셋/모델 → MODE 분기로 serve/smoke/idle).
# 베이스 CMD 를 비워(args 가 스크립트로 안 새게) 우리 스크립트만 PID1 로 돈다.
ENTRYPOINT ["bash", "/app/pod_start.sh"]
CMD []
