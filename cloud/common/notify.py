"""임의의 Discord 채널로 한 줄 마일스톤을 push (파드 스크립트가 진행을 남기는 다리).

`train_flow.py` 는 파이썬이라 `utils.discord.send_discord` 를 직접 부르지만, serve 파드는
bash(`pod_start.sh`·`serve_policy.sh`)로 도니 파이썬 호출이 필요하다. 이 얇은 CLI 가 그
다리 — bash 가 `python3 /app/notify.py "🟢 ready" --channel pipeline` 로 PIPELINE 등에
마일스톤을 남긴다(학습 파드가 PIPELINE 에 상세 로깅하는 것과 대칭).

파드-안전:
  - `scripts.env_config` 에 의존하지 않는다(파드 이미지엔 scripts/ 가 없다). 웹훅 URL 은
    이미 파드 env 에 있고 `send_discord` 가 os.environ 에서 직접 읽는다.
  - 웹훅 미설정이면 조용히 무시하고, 전송 실패도 삼킨다 — 관측이 파드 부팅/서빙을
    절대 막지 않는다(관측은 부가기능이지 게이트가 아니다).

전제: 해당 채널 웹훅 env (예 `PIPELINE_WEBHOOK_URL`). runpod_up._build_env 가 파드로 전달.
  - CLI: python cloud/common/notify.py "메시지" [--channel pipeline|runpod|stdout|ai-reporting|boot-timing]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))  # utils.discord (파드=/app, 로컬=cloud/common 둘 다 이 옆)

try:  # 로컬에서 부를 땐 .env 를 로드(파드는 env 가 이미 주입돼 있어 불필요·미존재).
    sys.path.insert(0, str(_HERE.parent.parent))  # project root (scripts.*)
    from scripts.env_config import load_env
except Exception:  # 파드: scripts/ 없음 → 그냥 os.environ 사용
    def load_env() -> None:
        pass

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass


def run(message: str, channel: str = "pipeline") -> None:
    """message 를 channel 로 보낸다. 실패해도 예외를 올리지 않는다(관측≠게이트)."""
    load_env()
    text = (message or "").strip()
    if not text:
        return
    try:
        from utils.discord import send_discord, DiscordChannel
    except Exception as e:  # utils import 실패도 부팅을 막지 않음
        print(f"[notify] utils.discord import 실패(무시): {e}")
        return
    try:
        ch = DiscordChannel(channel)
    except ValueError:
        ch = DiscordChannel.PIPELINE
    try:
        send_discord(text, channel=ch)  # 웹훅 없으면 send_discord 가 조용히 무시
        print(f"[notify:{ch.value}] {text}")
    except Exception as e:
        print(f"[notify] send 실패(무시): {e}")


def _cli() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("message", help="보낼 한 줄 ('-' 면 stdin 에서 읽음)")
    p.add_argument("--channel", default="pipeline",
                   help="pipeline|runpod|stdout|ai-reporting|boot-timing (기본 pipeline)")
    args = p.parse_args()
    msg = sys.stdin.read() if args.message == "-" else args.message
    run(msg, channel=args.channel)


if __name__ == "__main__":
    _cli()
