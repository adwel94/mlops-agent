# RunPod 운영 규칙 (단일 출처)

학습·평가로 RunPod GPU 파드를 띄우는 모든 스킬(`gr00t_train` · `gr00t_serve` ·
`gr00t_eval`)이 따르는 **공통 규칙**. 각 스킬 문서는 이 파일을 **참조만** 하고 규칙을
복제하지 않는다 — 규칙이 바뀌면 여기 한 곳만 고친다(스킬엔 고유 신호만 남긴다).

> 과금 파드다. 명시 요청 시에만 띄우고, 끝나면 반드시 종료(§4).

## 폴링 방식 (공통 메커니즘)

파드 상태는 하네스가 못 추적하는 외부 상태 — 자동 알림이 없으니 직접 폴링한다.

- `Bash` `run_in_background` 로 `sleep <N> && <확인>` → task-notification 으로 결과를 읽고
  다음 수를 판정한다. **일회성**(sleep 1 → 확인 1 → 판정), 턴 기반.
- **포그라운드 `sleep` 금지**(막힘), **루프 데몬 금지**(한 턴에 한 번만).
- 확인 도구: `runpod_client.pod(id)`(상태·IP·포트), `cloud/train/read_logs.py`(파드 stdout),
  `cloud/train/wandb_status.py`(학습 지표), `cloud/runpod/runpod_ls.py`(목록).

## 1. 부트스트랩 확인 (5분 주기)

파드를 띄우면 부팅이 제대로 진행되는지 **5분 단위**로 확인한다.

- **불량 호스트 조기 감지** — 생성 직후 `publicIp` 확인. `notes/cloud-ops-log.md` 의 불량
  호스트(`CUDA unknown error` 유발)와 같으면 부팅 완료를 기다리지 말고 즉시 `/runpod_down`
  후 `--cloud-type SECURE` 로 재기동(같은 community 풀은 또 그 호스트에 걸린다).
- **준비 신호** — 컨테이너 `RUNNING` 은 준비가 아니다(설치·다운로드·GPU 로드가 남음).
  - serve: **5555/tcp 바인딩**(TCP connect 또는 `PolicyClient.ping` 성공)
  - train: wandb 지표·`read_logs.py` 로그가 학습 단계로 진행
- ★ **부팅 로그 검증 — "받겠다고 한 것"과 "로그가 받은 것"을 대조** (2026-07-01 사건 규칙).
  `read_logs.py` 로 파드 stdout 을 보고 fetch 로그가 의도한 대상을 받았는지 확인한다:
  - 모델: `==> HF model download: <repo>@<revision>` 의 revision 이 **기대 태그인가?**
    특정 태그를 의도했는데 `@main` 이면 불일치 → **즉시 종료**(잘못된 체크포인트 평가 낭비
    방지). 근거: `--revision v2-s3000` 이 `@main` 으로 받힌 사건(→ `notes/cloud-ops-log.md`).
  - 데이터셋·이미지도 같은 원리로 대조.

## 2. 진행 리포팅·폴링 (최대 20분 주기, 필요시 더 짧게)

학습·평가 파이프라인이 도는 동안 중간중간 확인해 Discord 로 리포팅한다.

- 폴링 간격 **≤ 20분**, stall·이상 의심 시 더 짧게. **시작·추세 변화·완료·이상은 필수** 리포트.
- **AI 리포트는 `#ai-리포팅` 채널로만** (`cloud/train/ai_report.py "msg"`). 숫자는
  `wandb_status.py` 로 prose 에 녹인다. 파드가 직접 push 하는 채널(PIPELINE 진행바 / STDOUT
  raw)과 분리 — 폴링마다 추세 코멘트 1회 OK, 분 단위 도배 금지.

## 3. 연결 정보 (프로그램으로 획득)

- `publicIp` + `portMappings["5555"]`(매핑된 외부 포트) = `runpod_client.pod(pod_id)`.
  `runpod_ls` 는 포트를 안 보여주니 그걸로 묻지 말 것. proxy.runpod.net 은 HTTP 전용이라
  ZMQ(5555)엔 이 직접 TCP 매핑을 쓴다.

## 4. 종료 (과금 차단)

- 완료·실패·중단 어느 경우든 항상 `/runpod_down <pod_id>`. 파드 kill = 과금 중단 =
  무과금·가역이라 **승인 없이 자율**(CLAUDE.md 협업 규칙 #2).
- serve 는 서버가 죽어도 컨테이너를 idle 로 유지(restart-loop=조용한 과금 방지, 디버그 접속) →
  종료는 위 명령으로 명시적으로.
