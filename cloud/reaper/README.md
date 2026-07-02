# runpod-reaper — 파드 종료를 RunPod 밖에서 보장하는 Cloudflare Worker

## 두 기능

1. **크론 reaper (사람 통제)** — 15분마다 파드 목록을 보고 `MAX_AGE_HOURS`(기본 1h)를
   넘긴 RUNNING 파드가 있으면 Discord에 **🗑️ Terminate 버튼**과 함께 알림. 클릭 → 삭제.
   *(하드 크래시로 스스로 알리지도 못하고 떠버린 orphan 용 바닥 안전망.)*
2. **파드 자동 종료 (`/terminate`)** — 파드가 끝나면 3초마다 "죽여줘"를 보내고 Worker가
   실제 DELETE. 2번째 시도부터(이후 ~30초마다) 버튼 알람도 게시 → 자동이 막히면 사람이 클릭.

## 흐름

```
정상:  파드 끝 → /terminate 핑 → Worker DELETE → 파드 소멸 (조용)
지연:  3초 재시도 + (시도 2,12,22…) 버튼 알람 + 파드 직접 plain 알림
크래시: 파드가 핑 못 보냄 → 15분 내 크론이 발견 → 버튼 알림
Worker 다운: 파드의 plain 직접 알림으로 사람이 알고 → 로컬 runpod_down 수동 종료
```

## 배포

```bash
npm i -g wrangler            # 1회
cd cloud/reaper
# wrangler.toml 의 CHANNEL_ID 를 RunPod 채널 ID 로 교체 (Discord 개발자모드 → 채널 우클릭 → ID 복사)

wrangler secret put RUNPOD_API_KEY      # .env 의 RUNPOD_API_KEY
wrangler secret put DISCORD_BOT_TOKEN   # maniskill 봇 토큰
wrangler secret put DISCORD_PUBLIC_KEY  # Discord 포털 → 앱 → General Information → Public Key
wrangler secret put POD_PING_SECRET     # 아무 랜덤 문자열 (아래 .env 와 동일하게)

wrangler deploy             # → https://runpod-reaper.<계정>.workers.dev
```

## Discord 설정 (콘솔)

1. Discord Developer Portal → 앱(maniskill) → **General Information** →
   **Interactions Endpoint URL** = `https://runpod-reaper.<계정>.workers.dev/interactions`
   저장 시 Discord가 PING을 보내 검증 → Worker가 서명검증+PONG 하면 저장됨
   (실패하면 `DISCORD_PUBLIC_KEY` 확인).
2. 봇(maniskill)이 서버에 있고 RunPod 채널에 **메시지 보내기** 권한이 있어야 함.

## 프로젝트 `.env` 에 추가 (파이프라인이 파드로 전달)

```
WORKER_TERMINATE_URL=https://runpod-reaper.<계정>.workers.dev/terminate
POD_PING_SECRET=<위 wrangler secret 과 동일한 랜덤 문자열>
```

`launch_train.py` 가 이 둘을 파드 env 로 넘긴다 (`_SECRET_KEYS`). 파드의 `request_termination`
이 `WORKER_TERMINATE_URL` 로 핑한다.

## 테스트 (파드 없이)

```bash
# 1) 버튼 게시 확인
curl -X POST https://runpod-reaper.<계정>.workers.dev/terminate \
  -H "content-type: application/json" \
  -d '{"pod_id":"test123","secret":"<POD_PING_SECRET>","attempt":2}'
# → 채널에 버튼 메시지가 떠야 함. 클릭 → "종료 실패(test123 없음)" 면 인터랙션 경로 정상.
```

## 주의

- **3초 응답 한도**: 버튼 클릭 후 Worker는 3초 내 응답. RunPod DELETE 한 번이라 보통 OK.
- **버튼이 작동하려면 메시지를 봇이 게시**해야 함 → Worker가 봇 토큰으로 게시 (웹훅 메시지의
  버튼은 인터랙션이 라우팅 안 됨).
- 시크릿은 전부 Worker secret / `.env` (절대 커밋 금지, URL 노출 금지).
