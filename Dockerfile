# Thin 커스텀 이미지: RunPod 공식 베이스 + 가벼운 하네스 스크립트만.
#
# 설계(= 사용자 RunPod 팁): 무거운 의존성(GR00T clone + uv sync: torch/flash-attn)도,
# apt 패키지도 이미지에 RUN 으로 굽지 않는다 — 그러면 수 GB짜리 캐시되지 않는 레이어가
# 생겨 빌드/푸시/콜드풀이 느리고, 박힌 torch/CUDA 가 런타임 GPU·GR00T 핀과 어긋날 수 있다.
# 대신 가벼운 스크립트만 COPY 하고, 설치·데이터셋 다운로드·서버 실행은 전부 ENTRYPOINT
# (= 컨테이너 시작 시점)인 pod_start.sh 에서 한다 → 이미지 레이어는 수십 KB, 빌드 즉시.
#
# 빌드/푸시 (프로젝트 루트에서):
#   docker build -t adwel94/maniskill-gr00t:0.2 -t adwel94/maniskill-gr00t:latest .
#   docker push adwel94/maniskill-gr00t:0.2 && docker push adwel94/maniskill-gr00t:latest
# 사용: /runpod_up (env MODE/HF_DATASET 전달) → 파드가 부팅 때 스스로 설치·서빙 (SSH 불필요).

FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

WORKDIR /app

# cloud/runpod 스크립트만 COPY (pod_start/bootstrap/fetch_dataset/smoke_test/serve_policy.sh
# + new_embodiment_config.py). /workspace 는 RunPod 영속 볼륨 마운트 지점이라 거기 구우면
# 부팅 때 덮어써짐 → /app 사용. 데이터셋(lerobot)은 굽지 않고 부팅 때 HF Hub 에서 받음.
COPY cloud/runpod/ /app/

# ENTRYPOINT = 부팅 시 자급식 프로비저닝 (설치 → 데이터셋 → MODE 분기로 serve/smoke/idle).
# 베이스 CMD 를 비워(args 가 스크립트로 안 새게) 우리 스크립트만 PID1 로 돈다.
ENTRYPOINT ["bash", "/app/pod_start.sh"]
CMD []
