"""범용 슬립 래퍼 — 자고 나서 `--do` 를 실행하고 `--todo` 를 크게 되띄운다.

슬립 경계가 바로 다음에 뭘 할지 까먹는 지점이다. 그래서 슬립 자체를 소유 아티팩트로
만들어 두 가지를 얹는다: ① `--do` = 깨어나서 반드시 돌릴 명령(학습이면 train_watch.py —
수집+채널 보고가 그 안에서 강제된다). ② `--todo` = 내가 지금 적어두는 "깨어나서 할 일"
자연어 노트 → 깨어날 때 다시 떠서 실행을 상기시킨다. 보고 강제(①) + 의도 전달(②)의 결합.

에이전트는 이걸 `Bash run_in_background` 로 띄운다(내부 sleep 은 백그라운드라 무해).
완료 알림이 오면 출력 파일을 읽어 ①의 결과와 ②의 노트를 본다.

  - CLI: python cloud/common/poll.py --after 1200 \
             --do "python cloud/train/train_watch.py --pod-id X --label '...'" \
             --todo "완료면 서빙 승인 요청 / 아직이면 다음 폴 예약"
"""
from __future__ import annotations

import shlex
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def run(after: int, do: str | None = None, todo: str | None = None) -> int:
    """after 초 자고 do 를 실행, 끝에 todo 를 배너로 출력. do 의 종료코드 반환.

    do 는 shlex 로 argv 분해해 프로그램을 직접 exec 한다(nested 셸 없음) — Windows 도
    forward-slash exe 경로를 CreateProcess 로 받으므로 Git Bash/WSL bash 모호성을 피한다.
    파이프·리다이렉트 같은 셸 기능은 안 쓴다(단일 명령 실행 전용).
    """
    if after > 0:
        time.sleep(after)
    rc = 0
    if do:
        print(f"[poll] 깨어남 → 실행: {do}\n" + "-" * 60)
        proc = subprocess.run(shlex.split(do), text=True)
        rc = proc.returncode
        print("-" * 60 + f"\n[poll] --do 종료코드 {rc}")
    if todo:
        print("\n" + "=" * 60)
        print("다음 할 일 (poll 깨어남):")
        for line in todo.splitlines() or [todo]:
            print("  " + line)
        print("=" * 60)
    return rc


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--after", type=int, required=True, help="깨어나기까지 잘 초")
    p.add_argument("--do", default=None, help="깨어나서 실행할 명령 (shlex argv 로 직접 exec)")
    p.add_argument("--todo", default=None, help="깨어날 때 되띄울 자연어 할 일 노트")
    args = p.parse_args()
    rc = run(after=args.after, do=args.do, todo=args.todo)
    sys.exit(rc)


if __name__ == "__main__":
    _cli()
