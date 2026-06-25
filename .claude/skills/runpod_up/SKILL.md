---
name: runpod_up
description: RunPod GPU 파드를 생성한다 (GR00T 학습/평가용). cloud/runpod/runpod_up.py 래퍼 — runpod_client.create 위의 얇은 래퍼로, 베이스 이미지의 jupyter/ssh 를 유지하고(부팅 시 설치 패턴) 기본 포트에 8888/http·22/tcp·5555/tcp(④ 평가 정책 서버) 를 연다. RUNPOD_API_KEY 환경변수 필요. args는 `[--name N] [--gpu GPUType이름] [--volume GB] [--container-disk GB] [--image IMG] [--cloud-type COMMUNITY|SECURE]` 옵션; 비어있으면 name=gr00t, gpu=NVIDIA_L40S(48GB), volume=60, disk=40 기본값. 실제 클라우드 자원을 켜는(=과금) 작업이므로 무심코 부르지 말 것.
---

# runpod_up — RunPod GPU 파드 생성

`cloud/runpod/runpod_up.py` 래퍼. GR00T 스모크(①)·평가(④)·파인튜닝을 위한 GPU 파드를 띄운다. `dockerStartCmd` 를 건드리지 않아 베이스 이미지의 jupyter/ssh 가 살아있고, SSH 접속 후 `bootstrap.sh` → `smoke_test.sh` / `serve_policy.sh` 를 수동 실행하는 흐름(RunPod 팁 "부팅 시 설치"와 정합).

기본 포트에 **5555/tcp** 가 포함돼 ④ 평가용 정책 서버(`serve_policy.sh`)를 바로 노출할 수 있다.

> **과금 주의**: 실제 GPU 파드를 켜는 외부 작업이다. 사용자가 명시적으로 요청했을 때만 실행하고, 끝나면 `/runpod_down` 으로 반드시 종료.

## 전제조건

- `RUNPOD_API_KEY` 환경변수 (미설정이면 스크립트가 명확히 실패). 사용자가 셸에서 `! export RUNPOD_API_KEY=...` 로 넣도록 안내.

## 호출됐을 때

1. `args` 파싱 (모두 선택):
   - `--name <N>` (기본 `gr00t`), `--gpu <GPUType 이름>` (기본 `NVIDIA_L40S`; 예 `NVIDIA_A100_80GB_PCIE`)
   - `--volume <GB>` (기본 60, `/workspace` 영속), `--container-disk <GB>` (기본 40)
   - `--image <IMG>`, `--cloud-type COMMUNITY|SECURE`, `--port`(반복)
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe cloud\runpod\runpod_up.py [옵션]
   ```
3. 출력: `pod_id`, 상태/비용 요약, 그리고 다음 단계 런북(전송→bootstrap→smoke/serve→down).

## 동작 / 주의사항

- 스모크/평가는 3B 로드+optimizer 라 48GB(L40S) 권장. 본 파인튜닝은 A100 80GB 급.
- 패키지는 굽지 않고 컨테이너 부팅 시 설치(`bootstrap.sh`) — 빠른 부팅 + 캐시 효율.
- 종료를 잊으면 계속 과금 → 작업 후 `/runpod_ls` 로 확인하고 `/runpod_down` 으로 종료.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/runpod_up` | L40S·볼륨60·디스크40 파드 생성 (name=gr00t) |
| `/runpod_up --name ft --gpu NVIDIA_A100_80GB_PCIE --volume 100` | 본 파인튜닝용 A100 파드 |

흐름: **`/runpod_up`** → (SSH·전송·bootstrap) → `smoke_test.sh`/`serve_policy.sh` → `/runpod_down`.
