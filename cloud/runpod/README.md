# cloud/runpod — RunPod API 원자

RunPod REST API 와 대화하는 원시 동작 — 파드 생성·조회·종료.

| 파일 | 역할 | 스킬 |
|---|---|---|
| `runpod_client.py` | RunPod REST 클라이언트 — 파드 생성/조회/삭제, `GPUType`/`CloudType` | — |
| `runpod_up.py` | 파드 생성 (MODE·이미지·포트·env 조립) | `/runpod_up` |
| `runpod_ls.py` | 떠 있는 파드 + 시간당 비용 (읽기 전용) | `/runpod_ls` |
| `runpod_down.py` | 파드 종료 (과금 차단) | `/runpod_down` |
