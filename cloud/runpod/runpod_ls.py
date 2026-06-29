"""RunPod 파드 목록 + 상태 + 시간당 비용 (스킬: /runpod_ls).

runpod_client.pods 위의 얇은 래퍼 — "나 지금 뭐 켜놨지?" 를 비용과 함께 본다.
켜둔 채 잊으면 과금되므로 /runpod_down 으로 끄기 전에 먼저 확인하는 용도.

사전: export RUNPOD_API_KEY=...
  - Python:  from runpod_ls import run; run()
  - CLI:     python cloud/runpod/runpod_ls.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 가 ≈/합계 같은 비ASCII 출력에서 깨지는 것 방지
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root (scripts.*)
sys.path.insert(0, _HERE)
from scripts.env_config import load_env  # noqa: E402
from runpod_client import pods  # noqa: E402

load_env()  # .env -> RUNPOD_API_KEY


def _gpu(p: dict) -> str:
    """pod dict 에서 GPU 표기 추출 (스키마 변동에 방어적)."""
    n = p.get("gpuCount", "")
    g = p.get("machine", {}).get("gpuDisplayName") or p.get("gpuTypeId") or ""
    return f"{n}x {g}".strip() if g else str(n)


def run() -> list[dict]:
    """전체 파드를 출력하고 리스트를 반환. running 파드의 $/hr 합계도 표시."""
    plist = pods() or []
    if not plist:
        print("[runpod_ls] 떠 있는 파드 없음.")
        return plist

    print(f"[runpod_ls] {len(plist)} pod(s):")
    print(f"  {'ID':<20} {'NAME':<18} {'STATUS':<10} {'$/hr':>7}  GPU")
    running_cost = 0.0
    for p in plist:
        status = str(p.get("desiredStatus", "?"))
        cost = p.get("costPerHr") or 0.0
        try:
            cost = float(cost)
        except (TypeError, ValueError):
            cost = 0.0
        if status.upper() == "RUNNING":
            running_cost += cost
        print(f"  {str(p.get('id','?')):<20} {str(p.get('name','?'))[:18]:<18} "
              f"{status:<10} {cost:>7.3f}  {_gpu(p)}")
    print(f"\n[runpod_ls] running 합계 ≈ ${running_cost:.3f}/hr "
          f"(켜둔 파드는 /runpod_down 으로 종료)")
    return plist


def _cli() -> None:
    import argparse
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    run()


if __name__ == "__main__":
    _cli()
