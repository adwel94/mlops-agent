"""AI(에이전트)의 자연어 리포트를 #ai-리포팅(AI_REPORTING) 채널로 push.

`wandb_status.py` 가 메트릭 글랜스(숫자 표)라면, 이쪽은 **AI 의 자연어 해석·판단**을
그대로 채널에 보낸다 — "순항 중, loss 0.10 평탄화, 2h 뒤 완료 예정, 다음 폴링 30분 뒤"
같은 코멘트. 숫자는 wandb_status 로 보고 prose 에 녹여 쓴다(이 도구는 텍스트만 보냄).

운용: 파드-push 채널(RUNPOD/PIPELINE/STDOUT)과 분리된 **AI-push 전용** 채널.
      **의미 있는 순간(시작·주목할 추세변화·완료·이상)에만**, 매 폴링 도배 금지.

전제: `.env` 의 `AI_REPORTING_WEBHOOK_URL`.

  - CLI: python cloud/train/ai_report.py "학습 순항 중 — loss 0.10 평탄화, ~2h 뒤 완료 예정"
         echo "여러 줄\n리포트" | python cloud/train/ai_report.py -
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "cloud" / "runpod"))  # utils.discord
from scripts.env_config import load_env  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")  # Windows cp949 가 UTF-8 stdin(이모지/한글)을 깨뜨리는 것 방지
except Exception:
    pass


def run(message: str) -> str:
    """자연어 message 를 AI_REPORTING 채널로 보내고 반환한다."""
    load_env()
    text = message.strip()
    if not text:
        raise SystemExit("[ai_report] 빈 메시지 — 보낼 내용 없음.")
    if not os.getenv("AI_REPORTING_WEBHOOK_URL"):
        raise SystemExit("[ai_report] AI_REPORTING_WEBHOOK_URL 미설정 — .env 확인.")
    from utils.discord import send_discord, DiscordChannel  # noqa: E402

    send_discord(text, channel=DiscordChannel.AI_REPORTING)
    print("[ai_report] #ai-리포팅 push:\n" + text)
    return text


def _cli() -> None:
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("message", help="채널로 보낼 자연어 메시지 ('-' 면 stdin 에서 읽음)")
    args = p.parse_args()
    msg = sys.stdin.read() if args.message == "-" else args.message
    run(msg)


if __name__ == "__main__":
    _cli()
