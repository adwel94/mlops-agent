---
name: gr00t_serve
description: 파인튜닝된 GR00T 모델을 RunPod GPU 파드에서 정책 서버(5555/tcp)로 서빙한다 (④ 평가용). cloud/runpod/serve_up.py 래퍼 — runpod_up 의 MODE=serve 에 서빙 기본값(A5000 24GB, hf_model 필수, 5555 포트)을 박은 얇은 전용 래퍼. 파드가 부팅 때 스스로 bootstrap → fetch_model(HF 체크포인트 다운로드, 체크포인트 제외=최종 모델만) → serve_policy 를 자급 실행. RUNPOD_API_KEY(+private repo 면 HF_TOKEN) 환경변수 필요. args는 `<hf_model> [--name N] [--gpu GPUType이름] [--hf-model-subdir SUB] [--volume GB] [--container-disk GB] [--image IMG] [--cloud-type COMMUNITY|SECURE]`; hf_model 만 필수, 나머지는 서빙 기본값. 실제 GPU 파드를 켜는(=과금) 작업이므로 사용자가 명시 요청했을 때만 실행하고 끝나면 /runpod_down 으로 종료.
---

# gr00t_serve — GR00T 정책 서버 파드 생성 (④ 평가용)

`cloud/runpod/serve_up.py` 래퍼. 파인튜닝된 GR00T 체크포인트를 HF Hub 에서 받아 ZMQ 정책 서버(5555/tcp)로 띄운다. WSL 평가 클라이언트(`/gr00t_eval` 미정의 — 현재는 `scripts/gr00t_eval.py` 직접 호출)가 이 서버에 붙어 sim 롤아웃을 돌린다.

서빙은 `runpod_up` 의 한 *모드*(MODE=serve)일 뿐이라, 이 스킬은 거기에 서빙 기본값만 박은 얇은 래퍼다 (`/gr00t_serve <repo>` 한 줄). 파드는 부팅 때 SSH 없이 스스로: **bootstrap → fetch_model(HF 모델 다운로드) → serve_policy(5555/tcp)**.

> **과금 주의**: 실제 GPU 파드를 켜는 외부 작업이다. 사용자가 명시적으로 요청했을 때만 실행하고, 평가가 끝나면 `/runpod_down` 으로 반드시 종료.

## 전제조건

- `RUNPOD_API_KEY` 환경변수 (.env 자동 로드). 미설정이면 명확히 실패.
- private/gated HF repo 면 `HF_TOKEN` 도 필요 (파드로 전달돼 다운로드에 쓰임).
- 서빙할 모델이 HF Hub 에 **최종 모델 형상**(루트에 config + *.safetensors)으로 올라가 있어야 함 — `gr00t_train` 의 업로드가 이 형상을 보장.

## 호출됐을 때

1. `args` 파싱:
   - `<hf_model>` (필수, 위치 인자) — 서빙할 파인튜닝 모델 repo id (예 `adwel94/gr00t-threecubes-ft`)
   - `--gpu <GPUType 이름>` (기본 `NVIDIA_RTX_A5000`=24GB; 3B 로드에 충분)
   - `--hf-model-subdir <SUB>` (구 nested 레이아웃 호환; 보통 불필요)
   - `--name`, `--volume`(기본 40), `--container-disk`(기본 40), `--image`, `--cloud-type`
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe cloud\runpod\serve_up.py <hf_model> [옵션]
   ```
3. 출력: `pod_id`, 상태/비용 요약, 그리고 5555 가 뜬 뒤 WSL 에서 돌릴 평가 명령 런북.

## 동작 / 주의사항

- 3B 모델 로드는 24GB 면 OK(A5000 검증됨, ~$0.27/hr). OOM 나면 더 큰 GPU 로.
- 모델은 굽지 않고 부팅 때 HF 에서 받음 — 이미지 + repo id + 토큰만으로 자급.
- 서버가 죽어도 컨테이너는 idle 유지(restart-loop=조용한 과금 방지, 디버그 접속 유지) → **종료는 사용자가 명시적으로** `/runpod_down`.
- 연결 정보(publicIp + 5555 매핑포트)는 `/runpod_ls` 또는 RunPod 콘솔에서 확인. proxy.runpod.net 은 HTTP 전용이라 ZMQ 엔 직접 TCP 매핑을 써야 함.
- 평가는 별도(현재 `scripts/gr00t_eval.py`). 평가 기준이 정해지면 `/gr00t_eval` 스킬로 분리 예정.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/gr00t_serve adwel94/gr00t-threecubes-ft` | A5000 파드에 해당 모델 정책 서버 기동 |
| `/gr00t_serve adwel94/gr00t-threecubes-ft --gpu NVIDIA_L40S` | 48GB 로 서빙(여유) |

흐름: `gr00t_train`(학습) → **`/gr00t_serve <repo>`** → (WSL `gr00t_eval.py` 롤아웃) → `/runpod_down`.
