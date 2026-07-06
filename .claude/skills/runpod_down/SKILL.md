---
name: runpod_down
description: RunPod 파드를 종료한다 (과금 중단). cloud/runpod/runpod_down.py 래퍼 — runpod_client.delete 위의 래퍼로 **삭제 전 확인** 게이트 내장. 기본은 드라이런(무엇을 지울지만 보여주고 실제로는 안 지움), --yes 를 줘야 실제 삭제. RUNPOD_API_KEY 환경변수 필요. args는 `[pod_id] [--all] [--yes]`; pod_id 또는 --all 중 하나 필수. 되돌릴 수 없는 삭제이므로 반드시 먼저 드라이런으로 대상을 사용자에게 보여주고 동의를 받은 뒤 --yes 로 재실행.
---

# runpod_down — RunPod 파드 종료 (삭제 전 확인)

`cloud/runpod/runpod_down.py` 래퍼. 파드를 삭제해 과금을 멈춘다. 실수 삭제/과금을 막으려고 **기본은 드라이런** — 대상(이름·상태·$/hr)만 보여주고 실제로는 안 지운다. `--yes` 를 줘야 실제 삭제.

> 삭제는 **되돌릴 수 없다.** 항상 ① 드라이런으로 대상 표시 → ② 사용자에게 확인 → ③ 동의 시 `--yes` 로 재실행. 사용자 확인 없이 `--yes` 를 붙이지 말 것.

## 전제조건

- `RUNPOD_API_KEY` 환경변수.

## 호출됐을 때

1. `args` 파싱:
   - `pod_id` (위치 인자) **또는** `--all` (전체 파드) — 둘 중 하나 필수
   - `--yes` — 실제 삭제 (없으면 드라이런)
2. **1단계 (드라이런)**: 먼저 `--yes` 없이 실행해 종료 대상을 출력:
   ```
   <maniskill-python> cloud/runpod/runpod_down.py <pod_id>
   ```
   (대상이 헷갈리면 먼저 `/runpod_ls` 로 id 확인.)
3. 출력된 대상을 사용자에게 보여주고 **삭제 확인**을 받는다.
4. **2단계 (실제 삭제)**: 동의하면 동일 명령에 `--yes` 추가:
   ```
   ...runpod_down.py <pod_id> --yes
   ```

## 동작 / 주의사항

- 드라이런은 삭제된 id 없음(빈 리스트), `--yes` 만 실제 삭제.
- `--all` 은 모든 파드를 한 번에 종료 — 특히 신중히, 반드시 드라이런으로 목록 확인 후.
- 대상 파드가 없으면 그 사실을 알리고 `/runpod_ls` 안내.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/runpod_down abc123` | 드라이런 — `abc123` 종료 대상 표시(미삭제) |
| `/runpod_down abc123 --yes` | `abc123` 실제 종료 |
| `/runpod_down --all` | 드라이런 — 전체 파드 표시(미삭제) |

흐름: `/runpod_up` → … → `/runpod_ls`(확인) → **`/runpod_down`**(종료).
