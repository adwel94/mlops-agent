#!/usr/bin/env python3
"""파드 stdout 을 Discord STDOUT 채널로 흘리는 경량 로그 시퍼 (순수 stdlib).

학습(entrypoint.sh)·서빙(pod_start.sh) 양쪽 ENTRYPOINT 가 부팅 **첫 줄부터** 전체 출력을
RUN_LOG 로 tee 하고 이 스크립트를 백그라운드로 띄운다. 주기적으로 로그의 새 바이트를 읽어
≤1900자 코드블록 청크로 `STDOUT_WEBHOOK_URL` 에 POST. 읽는 쪽(에이전트)은 봇 토큰으로 그
채널을 본다. RunPod 콘솔 로그를 외부에서 보기 위한 디버깅 인프라(SSH/로그 엔드포인트 불필요).

설계 의도:
- **줄 단위로 쏘지 않고 묶어서** 보낸다 — Discord rate limit(분당 ~30) 회피.
- `requests`/pip 의존 없음 — bootstrap 전(설치 전)에도 동작해야 부팅 실패를 잡는다.
- 바이트 오프셋 추적(이진 모드) — getsize 와 일관, 멀티바이트 드리프트 없음.

  python3 _log_shipper.py <logfile> [--interval 20] [--webhook URL]
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

_MAX = 1900  # Discord 2000자 한도 - 코드펜스(```)·여유


def _post(webhook: str, content: str) -> bool:
    data = json.dumps({"content": content}).encode("utf-8")
    # User-Agent 필수: 기본 'Python-urllib' 는 Discord/Cloudflare 가 차단(403 code 1010).
    req = urllib.request.Request(
        webhook, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "maniskill-log-shipper/1.0"},
    )
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=15):
                return True
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited — retry_after 만큼 대기
                try:
                    retry = float(json.loads(e.read().decode()).get("retry_after", 2))
                except Exception:
                    retry = 2.0
                time.sleep(retry + 0.5)
                continue
            return False
        except Exception:
            time.sleep(2)
            continue
    return False


def _chunks(text: str):
    """텍스트를 줄 경계 우선으로 ≤_MAX 청크 리스트로 분할."""
    out, buf = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > _MAX:           # 초장문 한 줄은 강제 분할
            out.append(line[:_MAX])
            line = line[_MAX:]
        if len(buf) + len(line) > _MAX:
            out.append(buf)
            buf = ""
        buf += line
    if buf:
        out.append(buf)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logfile")
    ap.add_argument("--interval", type=float, default=20.0)
    ap.add_argument("--webhook", default=os.getenv("STDOUT_WEBHOOK_URL", ""))
    a = ap.parse_args()

    if not a.webhook:
        print("[log_shipper] STDOUT_WEBHOOK_URL 없음 — 시퍼 비활성", file=sys.stderr)
        return

    offset = 0
    while True:
        try:
            if os.path.exists(a.logfile):
                size = os.path.getsize(a.logfile)
                if size < offset:          # 파일이 잘렸으면(회전) 리셋
                    offset = 0
                if size > offset:
                    with open(a.logfile, "rb") as f:
                        f.seek(offset)
                        raw = f.read()
                        offset = f.tell()
                    new = raw.decode("utf-8", errors="replace")
                    for c in _chunks(new):
                        c = c.rstrip("\n")
                        if c:
                            _post(a.webhook, "```\n" + c + "\n```")
                            time.sleep(1.0)   # 청크 간 간격(rate limit 여유)
        except Exception as e:
            try:
                _post(a.webhook, f"[log_shipper] error: {e}")
            except Exception:
                pass
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
