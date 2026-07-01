# cloud/runpod — RunPod API 원자

RunPod REST API 와 대화하는 **원시 동작만** 담는다 (파드 생성·조회·종료). 파드에 굽는
이미지·런타임 스크립트는 여기 없다 — serve 이미지는 `cloud/serve`, train 이미지는
`cloud/train`, 둘이 공유하는 인프라는 `cloud/common`.

| 파일 | 역할 | 스킬 |
|---|---|---|
| `runpod_client.py` | RunPod REST 클라이언트 — 파드 생성/조회/삭제, `GPUType`/`CloudType` | — |
| `runpod_up.py` | 파드 생성 (MODE·이미지·포트·env 조립) | `/runpod_up` |
| `runpod_ls.py` | 떠 있는 파드 + 시간당 비용 (읽기 전용) | `/runpod_ls` |
| `runpod_down.py` | 파드 종료 (과금 차단) | `/runpod_down` |

- 이 원자들 위에 `cloud/serve`·`cloud/train` 이 각자 이미지를 얹어 파드를 띄운다.
- 연결 정보(`publicIp`+`portMappings`)·불량 호스트 감지·폴링·종료 등 **운영 규칙은
  [`cloud/RUNPOD_OPS.md`](../RUNPOD_OPS.md)**.
