"""Discord STDOUT 채널을 봇 토큰으로 읽어 파드 stdout 을 재구성 (에이전트 모니터링).

파드는 `_log_shipper.py` 로 stdout 을 STDOUT_WEBHOOK_URL 채널에 흘린다. 이 도구는
그 채널을 **봇 토큰으로 읽어** 시간순으로 합쳐 출력한다 — SSH/로그 엔드포인트 없이
부팅~학습~실패까지 raw 로그를 본다. (webhook 은 송신 전용이라 읽기엔 봇이 필요.)

전제: 봇이 해당 서버 멤버이고 그 채널에 **View Channel + Read Message History** 권한.
      채널 ID 는 STDOUT_WEBHOOK_URL 을 GET 해 자동 추출(별도 env 불필요).

  - CLI:  python cloud/common/read_logs.py [--limit 80]
          python cloud/common/read_logs.py --webhook <URL> --limit 200
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.env_config import load_env  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_API = "https://discord.com/api/v10"


def _channel_id(webhook: str) -> str:
    """webhook URL 을 GET 해 channel_id 를 얻는다(인증 불필요)."""
    import requests

    r = requests.get(webhook, timeout=15)
    r.raise_for_status()
    cid = r.json().get("channel_id")
    if not cid:
        raise RuntimeError("webhook 응답에 channel_id 없음 — URL 확인.")
    return cid


def _fetch(channel_id: str, token: str, limit: int) -> list[dict]:
    """채널 메시지를 limit 개까지 가져온다(필요하면 before 페이지네이션)."""
    import requests

    headers = {"Authorization": f"Bot {token}"}
    out: list[dict] = []
    before = None
    while len(out) < limit:
        params = {"limit": min(100, limit - len(out))}
        if before:
            params["before"] = before
        r = requests.get(
            f"{_API}/channels/{channel_id}/messages",
            headers=headers, params=params, timeout=20,
        )
        if r.status_code == 401:
            raise RuntimeError("401 — DISCORD_BOT_TOKEN 무효.")
        if r.status_code == 403:
            raise RuntimeError("403 — 봇이 채널 접근 불가(서버 멤버/권한 확인: View Channel + Read Message History).")
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        before = batch[-1]["id"]
    return out


def _strip_fence(content: str) -> str:
    s = content.strip()
    if s.startswith("```") and s.endswith("```"):
        s = s[3:-3]
        if s.startswith("\n"):
            s = s[1:]
    return s


def run(limit: int = 80, webhook: str | None = None) -> str:
    """STDOUT 채널 최근 limit 개 메시지를 시간순 raw 로그로 합쳐 출력하고 반환."""
    load_env()
    webhook = webhook or os.getenv("STDOUT_WEBHOOK_URL")
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not webhook:
        raise RuntimeError("STDOUT_WEBHOOK_URL 미설정 — .env 확인.")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN 미설정 — .env 확인.")

    cid = _channel_id(webhook)
    msgs = _fetch(cid, token, limit)
    msgs.reverse()  # API 는 최신순 → 시간순으로
    text = "\n".join(_strip_fence(m.get("content", "")) for m in msgs if m.get("content"))
    print(text if text else "[read_logs] 채널에 메시지 없음 — 파드가 아직 안 보냈거나 webhook 채널이 다름.")
    return text


def _cli() -> None:
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--limit", type=int, default=80, help="가져올 최근 메시지 수 (기본 80)")
    p.add_argument("--webhook", default=None, help="STDOUT_WEBHOOK_URL 오버라이드")
    args = p.parse_args()
    run(limit=args.limit, webhook=args.webhook)


if __name__ == "__main__":
    _cli()
