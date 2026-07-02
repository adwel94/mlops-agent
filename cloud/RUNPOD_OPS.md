# RunPod 운영 규칙

학습·평가로 RunPod GPU 를 사용할 때 읽어봐야 될 규칙.

> 과금 파드다. 명시 요청 시에만 띄우고, 끝나면 반드시 종료.

## 관측 — 이 스크립트로 상태를 본다

| 스크립트 | 볼 수 있는 것 |
|---|---|
| `cloud/common/read_logs.py` | 파드 raw stdout (부팅·다운로드·기동·에러) |
| `cloud/train/wandb_status.py` | 학습 loss/lr 등 지표 |
| `cloud/common/ai_report.py "msg"` | #ai-리포팅 채널로 내가 리포트를 보냄 |
| BOOT_TIMING 채널 | 부팅 단계별 소요 — "부트스트랩 왜 느리지" 과거와 비교 (`read_logs.py --webhook`) |

PIPELINE·RUNPOD 채널은 파드가 Discord 에 올린다(사람이 봄).

## 폴링

파드 상태는 자동 알림이 없어 직접 확인한다. `Bash` `run_in_background` 로
`sleep <N> && <확인>` 을 돌려 알림으로 결과를 받고 다음 수를 정한다. 한 턴에 한 번,
포그라운드 `sleep` 금지.

## 부팅 확인 (5분 간격)

- **불량 호스트** — 생성 직후 `publicIp` 가 `notes/cloud-ops-log.md` 의 불량 호스트면 즉시
  종료 후 `--cloud-type SECURE` 로 재기동.
- **준비 신호** — `RUNNING` 은 아직 아님(다운로드·GPU 로드 남음). serve=5555 바인딩,
  train=지표·로그가 학습 단계로 진행.
- **받은 것 대조** — `read_logs.py` 로 fetch 로그를 보고 의도한 걸 받았는지 확인.
  예: 모델 다운로드 로그의 `@<revision>` 이 원한 태그인가(`@main` 이면 종료).

## 진행 리포팅 (20분 이하 간격)

돌아가는 동안 `ai_report.py` 로 #ai-리포팅 에 추세를 남긴다. 시작·변화·완료·이상은 필수, 도배 금지.

## 연결

`publicIp` + 5555 매핑 포트 = `runpod_client.pod(pod_id)`. (`runpod_ls` 는 포트 안 보임.)

## 종료

완료·실패·중단 어느 때든 `/runpod_down <pod_id>`.
