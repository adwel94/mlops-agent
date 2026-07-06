---
name: runpod_ls
description: 떠 있는 RunPod 파드 목록을 상태와 시간당 비용($/hr)과 함께 보여준다. cloud/runpod/runpod_ls.py 래퍼 — runpod_client.pods 위의 얇은 래퍼. "지금 뭐 켜놨지?" 를 비용과 함께 확인해 잊고 과금되는 일을 막고, /runpod_down 으로 끄기 전 대상 파악용. RUNPOD_API_KEY 환경변수 필요. 파라미터 없음.
---

# runpod_ls — RunPod 파드 목록 + 비용

`cloud/runpod/runpod_ls.py` 래퍼. 전체 파드를 `ID · NAME · STATUS · $/hr · GPU` 표로 출력하고, running 파드의 시간당 비용 합계를 보여준다. 켜둔 채 잊으면 과금되므로, `/runpod_down` 으로 종료하기 전에 무엇이 떠 있는지 먼저 확인하는 용도.

## 전제조건

- `RUNPOD_API_KEY` 환경변수.

## 호출됐을 때

1. 인자 없음.
2. 프로젝트 루트에서 실행:
   ```
   <maniskill-python> cloud/runpod/runpod_ls.py
   ```
3. 출력: 파드 표 + `running 합계 ≈ $X/hr`. 파드가 없으면 그 사실을 알림.

## 동작 / 주의사항

- 읽기 전용 — 아무것도 생성/삭제하지 않음.
- GPU/비용 필드는 RunPod 응답 스키마 변동에 방어적으로 추출(없으면 공란).

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/runpod_ls` | 전체 파드 + 상태 + $/hr 합계 |

흐름: `/runpod_up` → … → **`/runpod_ls`**(확인) → `/runpod_down`(종료).
