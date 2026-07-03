# GR00T 이미지 빌드/푸시 — 태그만 올려서 굽는다.
#
# 빌드는 amd64 호스트(Windows / Linux)에서 한다. thin 이미지(스크립트만 COPY)라 수초면 끝.
# Apple Silicon(arm64)에서는 buildx 가 필요하니 아래 참고:
#   make serve-push DOCKER="docker buildx" BUILDX_FLAGS="--platform linux/amd64 --push"
# (그 경우 serve-push 의 별도 push 는 생략 — --push 가 빌드에 포함됨.)
#
# 새 이미지를 구울 때는 아래 *_TAG 만 올린다. :latest 도 함께 태깅/푸시되어
# serve_up/launch_train 의 기본 이미지(:latest)가 자동으로 새 이미지를 집는다.

DOCKER ?= docker
REGISTRY ?= adwel94
BUILDX_FLAGS ?=

# 현재 태그 — 새로 구울 때 여기만 올린다.
SERVE_TAG ?= 0.5
TRAIN_TAG ?= 0.2

SERVE_IMAGE := $(REGISTRY)/maniskill-gr00t
TRAIN_IMAGE := $(REGISTRY)/maniskill-gr00t-train

.DEFAULT_GOAL := help
.PHONY: help serve serve-push train train-push

help:
	@echo "gr00t 이미지 빌드/푸시 (프로젝트 루트에서 실행)"
	@echo ""
	@echo "  make serve         - serve 이미지 빌드  $(SERVE_IMAGE):$(SERVE_TAG) (+ :latest)"
	@echo "  make serve-push    - serve 빌드 + push"
	@echo "  make train         - train 이미지 빌드  $(TRAIN_IMAGE):$(TRAIN_TAG) (+ :latest)"
	@echo "  make train-push    - train 빌드 + push"
	@echo ""
	@echo "  태그 오버라이드:   make serve-push SERVE_TAG=0.5"

serve:
	$(DOCKER) build $(BUILDX_FLAGS) -f cloud/serve/Dockerfile \
		-t $(SERVE_IMAGE):$(SERVE_TAG) -t $(SERVE_IMAGE):latest .

serve-push: serve
	$(DOCKER) push $(SERVE_IMAGE):$(SERVE_TAG)
	$(DOCKER) push $(SERVE_IMAGE):latest

train:
	$(DOCKER) build $(BUILDX_FLAGS) -f cloud/train/Dockerfile \
		-t $(TRAIN_IMAGE):$(TRAIN_TAG) -t $(TRAIN_IMAGE):latest .

train-push: train
	$(DOCKER) push $(TRAIN_IMAGE):$(TRAIN_TAG)
	$(DOCKER) push $(TRAIN_IMAGE):latest
