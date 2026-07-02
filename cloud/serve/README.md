# cloud/serve — GR00T 정책 서버 이미지 번들

파인튜닝된 GR00T 체크포인트를 ZMQ 정책 서버(5555/tcp)로 서빙하는 파드 이미지 + 클라이언트 런처.

thin 이미지 전략: 무거운 의존성(GR00T uv sync·flash-attn)과 모델은 이미지에 굽지 않고,
ENTRYPOINT(`pod_start.sh` = GPU 있는 RunPod 부팅 시점)에서 설치·다운로드한다.

| 파일 | 역할 |
|---|---|
| `serve_up.py` | 클라이언트 런처 — `runpod_up`(MODE=serve)에 서빙 기본값 박은 래퍼 (`/gr00t_serve`) |
| `Dockerfile` | serve 이미지 — `cloud/serve` + `cloud/common` → `/app`, ENTRYPOINT=`pod_start.sh` |
| `pod_start.sh` | ENTRYPOINT — bootstrap → fetch_model → MODE 분기(serve/smoke/idle) |
| `serve_policy.sh` | GR00T 정책을 5555/tcp 로 서빙 (fresh-process 재시도 루프) |
| `fetch_model.sh` / `fetch_dataset.sh` | 부팅 때 HF Hub 에서 모델/데이터셋 다운로드 |
| `smoke_test.sh` | 로드+스모크 (`launch_finetune --max-steps 2`) |
| `probe_dl/` | 다운로드·GPU 진단 스크립트 |

공유 인프라(bootstrap·new_embodiment_config·utils·_log_shipper)는 `cloud/common`, 파드
생성/종료 원자는 `cloud/runpod`.

## 이미지 빌드/푸시

```
docker build -f cloud/serve/Dockerfile -t adwel94/maniskill-gr00t:latest .
docker push adwel94/maniskill-gr00t:latest
```
프로젝트 루트에서 실행(빌드 컨텍스트=루트). `cloud/serve`·`cloud/common` 스크립트를 고치면 재빌드+푸시.
