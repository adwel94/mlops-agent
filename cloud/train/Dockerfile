# GR00T 학습 전용 thin 이미지 (서빙 cloud/runpod 와 분리).
#
# 서빙 이미지와 동일 철학: 무거운 의존성(GR00T uv sync, prefect 등)은 RUN 으로 굽지 않고
# ENTRYPOINT(entrypoint.sh)에서 부팅 시 설치(= GPU 있는 RunPod 환경 → flash-attn arch 정확).
# 여기선 가벼운 스크립트만 COPY.
#
# 빌드/푸시 (프로젝트 루트에서, -f 로 이 파일 지정):
#   docker build -f cloud/train/Dockerfile -t adwel94/maniskill-gr00t-train:0.4 -t adwel94/maniskill-gr00t-train:latest .
#   docker push adwel94/maniskill-gr00t-train:0.4 && docker push adwel94/maniskill-gr00t-train:latest
# 실행: python cloud/train/launch_train.py  (env 주입 → 파드가 부팅 때 학습 자급)

FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

WORKDIR /app

# 학습 파이프라인 스크립트 (entrypoint/options/train_flow/_gr00t_train/discord_callback)
COPY cloud/train/ /app/
# 공유 파드 인프라(cloud/common): GR00T 설치 스크립트 · modality config · Discord 유틸 · stdout 시퍼
COPY cloud/common/bootstrap.sh /app/bootstrap.sh
COPY cloud/common/new_embodiment_config.py /app/new_embodiment_config.py
COPY cloud/common/utils/ /app/utils/
COPY cloud/common/_log_shipper.py /app/_log_shipper.py

# CRLF 방역: Windows 빌드 호스트에서 스크립트가 CRLF 로 체크아웃되면 컨테이너 bash 가
# 'set: pipefail: invalid option name' 으로 부팅을 통째로 깨뜨린다 → 이미지 안에서 LF 강제.
RUN sed -i 's/\r$//' /app/*.sh

ENTRYPOINT ["bash", "/app/entrypoint.sh"]
CMD []
