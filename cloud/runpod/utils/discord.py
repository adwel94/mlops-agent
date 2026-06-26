"""Discord Webhook 유틸."""

import os
import time
import requests

from enum import Enum
from typing import Union

class DiscordChannel(Enum):
    RUNPOD = "runpod"        # 파드/인프라/과금 (생성·자가종료·종료실패 경보)
    PIPELINE = "pipeline"    # 학습 파이프라인 (시작·진행·완료·업로드·실패)
    STDOUT = "stdout"        # 파드 raw stdout 스트림 (에이전트가 봇 토큰으로 읽음)
    AI_REPORTING = "ai-reporting"  # AI(에이전트)가 push 하는 분석/추세 다이제스트 (파드 아님)

# 1. 사용할 채널들을 미리 등록합니다.
# 채널명: 환경변수명 (또는 직접적인 URL도 가능하지만 보안상 환경변수 권장)
DISCORD_CHANNELS = {
    DiscordChannel.RUNPOD: "RUNPOD_WEBHOOK_URL",
    DiscordChannel.PIPELINE: "PIPELINE_WEBHOOK_URL",
    DiscordChannel.STDOUT: "STDOUT_WEBHOOK_URL",
    DiscordChannel.AI_REPORTING: "AI_REPORTING_WEBHOOK_URL",
}

def send_discord(text: str, channel: Union[DiscordChannel, str] = DiscordChannel.PIPELINE, components: list = None):
    """
    Discord Webhook으로 메시지 전송.
    :param text: 전송할 메시지
    :param channel: DiscordChannel Enum 멤버 또는 등록된 키값 (기본값: DiscordChannel.PIPELINE)
    :param components: Discord 메시지 컴포넌트 (버튼 등)
    """
    # Enum이 아닌 문자열로 들어온 경우 Enum으로 변환 시도
    if isinstance(channel, str):
        try:
            channel = DiscordChannel(channel)
        except ValueError:
            print(f"  [discord] error: '{channel}'은(는) 등록되지 않은 채널입니다.")
            return

    env_var = DISCORD_CHANNELS.get(channel)
    if not env_var:
        return

    url = os.getenv(env_var)
    if not url:
        # URL이 설정되지 않은 경우 조용히 넘어감 (개발 환경 등)
        return

    # Discord 메시지 2000자 제한
    if len(text) > 2000:
        text = text[:1997] + "..."

    payload = {"content": text}
    if components:
        payload["components"] = components

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"  [discord:{channel}] error: {e}")


def _format_duration(seconds: float) -> str:
    """초를 MM:SS 또는 HH:MM:SS 문자열로 변환."""
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def send_progress_notification(title: str, current_step: int, total_steps: int, start_time: float, channel: Union[DiscordChannel, str] = DiscordChannel.PIPELINE):
    """tqdm 스타일 진행률 메시지 생성 및 Discord 전송."""
    progress_ratio = current_step / total_steps
    percentage = int(progress_ratio * 100)

    total_bars = 20
    filled = int(progress_ratio * total_bars)
    bar = "█" * filled + "░" * (total_bars - filled)

    elapsed = time.time() - start_time
    if current_step > 0:
        spd = elapsed / current_step
        eta = spd * (total_steps - current_step) + elapsed
        msg = f"{percentage:3d}%|{bar}| {current_step}/{total_steps} [{_format_duration(elapsed)}<{_format_duration(eta)}, {spd:.2f}s/it]"
    else:
        msg = f"{percentage:3d}%|{bar}| {current_step}/{total_steps}"

    send_discord(f"🔔 {title}\n{msg}", channel=channel)
