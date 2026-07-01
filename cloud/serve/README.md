# cloud/serve — GR00T 정책 서버 이미지 번들

파인튜닝된 GR00T 체크포인트를 ZMQ 정책 서버(5555/tcp)로 서빙하는 **파드 이미지 + 클라이언트
런처**. 평가(`scripts/gr00t_eval.py`, WSL)가 이 서버에 붙어 sim 롤아웃을 돌린다.

**thin 이미지 전략**: 무거운 의존성(GR00T uv sync·flash-attn)과 모델은 이미지에 굽지 않고,
ENTRYPOINT(`pod_start.sh` = GPU 있는 RunPod 부팅 시점)에서 설치·다운로드한다 → 이미지 레이어는
수십 KB, arch 정확, SSH 없이 `/gr00t_serve` 한 줄로 서버까지 자급.

| 파일 | 역할 |
|---|---|
| `serve_up.py` | **클라이언트 런처** — `runpod_up`(MODE=serve)에 서빙 기본값 박은 래퍼 (`/gr00t_serve`) |
| `Dockerfile` | serve 이미지 — `cloud/serve` + `cloud/common` → `/app`, ENTRYPOINT=`pod_start.sh` |
| `pod_start.sh` | ENTRYPOINT — bootstrap → fetch_model → MODE 분기(serve/smoke/idle) |
| `serve_policy.sh` | GR00T 정책을 5555/tcp 로 서빙 (fresh-process 재시도 루프) |
| `fetch_model.sh` / `fetch_dataset.sh` | 부팅 때 HF Hub 에서 모델/데이터셋 다운로드 (`HF_MODEL_REVISION` 지원) |
| `smoke_test.sh` | ① 로드+스모크 (`repair_lerobot_metadata` → `launch_finetune --max-steps 2`) |
| `probe_dl/` | 다운로드·GPU 진단 스크립트 |

- **공유 인프라**(bootstrap·new_embodiment_config·utils·_log_shipper)는 `cloud/common`.
- **파드 원자**(생성/종료)는 `cloud/runpod`. **운영·관측**(폴링·부팅로그 검증·비용·종료)은
  [`cloud/RUNPOD_OPS.md`](../RUNPOD_OPS.md).
- **평가 실행**: 서버가 5555 로 뜨면 이 PC WSL 에서 `scripts/gr00t_eval.py` 롤아웃
  (→ `gr00t_eval` 스킬 / RUNPOD_OPS). 입력은 소스 이미지 데이터셋 h5(LeRobot 디렉토리 아님).

## 이미지 빌드/푸시 (스크립트 변경 시)

```
docker build -f cloud/serve/Dockerfile -t adwel94/maniskill-gr00t:latest .
docker push adwel94/maniskill-gr00t:latest
```
프로젝트 루트에서 실행(빌드 컨텍스트 = 루트). 베이스 레이어는 이미 Docker Hub 에 있어
작은 스크립트 레이어만 올라감. `cloud/serve`·`cloud/common` 스크립트를 고치면 재빌드+푸시.

## 비용 메모

- 3B 로드는 24GB(A5000)면 OK(~$0.27/hr). 안정 라인은 L40S 48GB. OOM 나면 더 큰 GPU.
- 서버가 죽어도 컨테이너는 idle 유지(restart-loop=조용한 과금 방지) → 종료는 `/runpod_down`.
