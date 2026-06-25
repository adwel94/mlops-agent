# cloud/runpod — GR00T RunPod 테스트 번들

`h5_to_lerobot` 출력이 **GR00T-N1.7-3B 에서 실제로 로드/학습되는지**(① 로드+스모크)
RunPod GPU 에서 확인하는 번들.

**이미지 전략 (thin 커스텀 이미지 + 자급식 ENTRYPOINT):** 무거운 의존성(GR00T clone +
uv sync: torch/flash-attn)과 apt 패키지는 이미지에 `RUN` 으로 굽지 않는다 — 수 GB짜리
캐시 안 되는 레이어/버전 불일치를 피하기 위함. 대신 **가벼운 하네스 스크립트(cloud/runpod)만**
`/app` 에 COPY 하고, 설치·데이터셋 다운로드·서버 실행은 전부 **`ENTRYPOINT`(=컨테이너 시작
시점)** 인 `pod_start.sh` 에서 한다. 결과: 이미지 레이어 수십 KB(빌드/푸시 즉시), 파드가
**부팅 때 스스로 프로비저닝** → SSH 없이 `/runpod_up` 한 번으로 서버까지 뜸.

## 파일

| 파일 | 역할 |
|---|---|
| `../../Dockerfile` (프로젝트 루트) | thin 이미지 — 베이스 + `/app` 에 cloud/runpod COPY + ENTRYPOINT=pod_start.sh |
| `runpod_client.py` | RunPod REST API 클라이언트 (pod 생성/조회/삭제) |
| `runpod_up.py` / `runpod_ls.py` / `runpod_down.py` | 파드 운영 스킬 (`/runpod_up` 생성 · `/runpod_ls` 목록+비용 · `/runpod_down` 종료, 삭제 전 확인) |
| `pod_start.sh` | **ENTRYPOINT** — 부팅 시 자급식: ssh/jupyter→bootstrap→fetch_dataset→MODE 분기(serve/smoke/idle) |
| `bootstrap.sh` | 환경 셋업(부팅 시) — uv sync, ffmpeg, git-lfs, Isaac-GR00T clone (멱등) |
| `fetch_dataset.sh` | HF Hub 에서 LeRobot 데이터셋 다운로드 → `/workspace/lerobot` (`HF_DATASET` env) |
| `new_embodiment_config.py` | GR00T NEW_EMBODIMENT modality config (우리 `modality.json` 과 1:1) |
| `smoke_test.sh` | ① 로드+스모크 — `repair_lerobot_metadata` → `launch_finetune --max-steps 2` |
| `serve_policy.sh` | ④ sim 평가(서버측) — GR00T 정책을 ZMQ(5555/tcp)로 서빙 |

## 이미지 빌드/푸시 (1회 또는 스크립트 변경 시)

```
docker build -t adwel94/maniskill-gr00t:0.2 -t adwel94/maniskill-gr00t:latest .
docker push adwel94/maniskill-gr00t:0.2
docker push adwel94/maniskill-gr00t:latest
```
프로젝트 루트에서 실행(빌드 컨텍스트). 베이스 레이어는 Docker Hub 에 이미 있어 push 시
**작은 스크립트 레이어만** 올라감. cloud/runpod 스크립트를 고치면 재빌드+푸시.

## 흐름 (자급식 — SSH 불필요)

데이터셋은 한 번 HF Hub 에 올려두고(`hf upload <repo> ./lerobot --repo-type dataset`),
파드는 부팅 때 `HF_DATASET` env 로 받는다. 직접 전송 없음.

```
0. 비밀키: 프로젝트 루트 .env 에 RUNPOD_API_KEY, HF_TOKEN 채우기 (.env.example 복사)
1. (1회) 데이터셋을 HF private dataset repo 로 push
2. ① 스모크:  python cloud/runpod/runpod_up.py --mode smoke  --hf-dataset <repo>
   ④ 평가:    python cloud/runpod/runpod_up.py --mode serve  --serve-base --hf-dataset <repo>
        → 파드가 부팅 때 bootstrap → HF 데이터셋 → 스모크/서버 자동 실행
3. /runpod_ls 로 IP·5555 매핑포트 확인  (또는 RunPod 콘솔)
4. (서버일 때) 이 PC WSL 에서 scripts/gr00t_eval.py 로 롤아웃 (아래 ④ 절)
5. /runpod_down — 과금 중단
```

디버그가 필요하면 SSH/Jupyter 로 접속해 `/app/*.sh` 를 수동 실행할 수도 있다(MODE=idle).

## 핵심 매핑 (우리 데이터셋 ↔ GR00T config)

`new_embodiment_config.py` 의 `modality_keys` 는 `meta/modality.json` 키와 정확히 일치:

| | 키 | GR00T ActionConfig |
|---|---|---|
| state | `qpos`, `eef` | — (eef 가 상대화 기준 `state_key`) |
| action | `eef` | `EEF / RELATIVE / XYZ_ROT6D / state_key="eef"` |
| action | `gripper` | `NON_EEF / ABSOLUTE / DEFAULT` |
| video | `base_camera` | — |
| language | `human.task_description` | — |

액션 호라이즌 = 16 (`delta_indices=range(16)`, GR00T-N1.7 액션 헤드와 정합).

## 비용 메모

- ① 스모크: `--max-steps 2`, 몇 분. L40S(48GB)면 충분. 끝나면 **즉시 pod 삭제**.
- 본 파인튜닝(③): A100 80GB 급 권장 — 별도 단계.

## ④ sim 평가 (서버=pod / 롤아웃=내 PC WSL)

학습된(또는 베이스) 정책이 **실제로 task 를 성공시키는지** 측정. 의존성 충돌
(gr00t torch/numpy≥2 ↔ mplib numpy<2)을 피하려고 **정책 서버 ↔ 롤아웃 클라이언트**를
ZMQ 로 분리한다. 정책(GPU)은 pod, sim+IK 는 이미 다 갖춰진 내 WSL.

```
[pod GPU]  serve_policy.sh ──ZMQ/tcp:5555──►  [내 PC · WSL]  scripts/gr00t_eval.py
 GR00T 정책 서버                                 sim + mplib IK 롤아웃 (torch 없음)
```

```
# pod 측 (서버) ─ 5555/tcp 를 RunPod 콘솔에서 expose 해 두고:
MODEL_PATH=/workspace/outputs/<run>/checkpoint-XXXX \
    bash /app/serve_policy.sh
#   베이스 모델 baseline: SERVE_BASE=1 DATASET_DIR=/workspace/lerobot bash serve_policy.sh

# 내 PC 측 (롤아웃) ─ WSL maniskill env 에 한 번만:  pip install pyzmq msgpack msgpack-numpy
python scripts/gr00t_eval.py \
    --traj-path data/datasets/<task>/<...>.rgb.pd_joint_pos.physx_cpu.h5 \
    --server-host <RunPod proxy host> --server-port <proxy port> \
    --instruction "pick up the {target_id} cube" --count 20
#   → DONE gr00t_eval ... policy_success=N/20 success_rate=0.xx
```

- **입력은 소스 이미지 데이터셋 h5** (lerobot 디렉토리 아님) — 롤아웃이 씬 reset 용
  `episode_seed` 와 지시문 생성용 `label_metadata` 를 필요로 함. `ee_verify` 와 동일.
- 모델 출력 = **절대 EEF**(서버가 `state_key="eef"` 로 내부 un-relativize). `rot6d→quat`
  (`scripts/ee_convert.rot6d_to_quat`) → world 목표 pose → `scripts/ik_exec` 의 mplib IK.
- IK 플러밍은 `ee_verify` 와 **공통 모듈 `scripts/ik_exec.py`** 로 공유.

## ② 오버핏/제대로 학습되는 환경 (이 번들 밖)

- 스텝수 조절로 로스 수렴을 보는 본격 학습 파이프라인 — 별도 설계 단계.
