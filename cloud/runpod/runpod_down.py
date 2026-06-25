"""RunPod 파드 종료 (스킬: /runpod_down). **삭제 전 확인** 게이트 내장.

runpod_client.delete 위의 래퍼. 실수 과금/삭제를 막으려고 기본은 **드라이런** —
무엇을 지울지(이름·상태·$/hr)만 보여주고 실제로는 안 지운다. `--yes` 를 줘야 실제
삭제. 스킬 흐름: 먼저 드라이런 → 사용자에게 대상 확인 → 동의하면 --yes 로 재실행.

사전: export RUNPOD_API_KEY=...
  - Python:  from runpod_down import run; run("pod_id", yes=True)
  - CLI:     python cloud/runpod/runpod_down.py <pod_id>          # 드라이런(미삭제)
             python cloud/runpod/runpod_down.py <pod_id> --yes    # 실제 삭제
             python cloud/runpod/runpod_down.py --all --yes       # 전체 삭제
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root (scripts.*)
sys.path.insert(0, _HERE)
from scripts.env_config import load_env  # noqa: E402
from runpod_client import delete, pods  # noqa: E402

load_env()  # .env -> RUNPOD_API_KEY


def _targets(pod_id: str | None, all_pods: bool) -> list[dict]:
    plist = pods() or []
    if all_pods:
        return plist
    return [p for p in plist if str(p.get("id")) == str(pod_id)]


def run(pod_id: str | None = None, all_pods: bool = False, yes: bool = False) -> list[str]:
    """파드를 종료한다. yes=False 면 드라이런(대상만 출력, 삭제 안 함).

    삭제된 pod_id 목록을 반환 (드라이런이면 빈 리스트).
    """
    if not pod_id and not all_pods:
        raise ValueError("pod_id 를 주거나 all_pods=True 를 지정하세요.")

    targets = _targets(pod_id, all_pods)
    if not targets:
        which = "전체" if all_pods else pod_id
        print(f"[runpod_down] 대상 파드 없음 ({which}). /runpod_ls 로 확인하세요.")
        return []

    print(f"[runpod_down] 종료 대상 {len(targets)} 개:")
    for p in targets:
        cost = p.get("costPerHr") or 0.0
        print(f"  - {p.get('id')}  {p.get('name')}  [{p.get('desiredStatus')}]  ${cost}/hr")

    if not yes:
        ids = " ".join(str(p.get("id")) for p in targets)
        print("\n[runpod_down] 드라이런 — 아무것도 삭제하지 않았습니다.")
        print(f"  실제 종료하려면:  python cloud/runpod/runpod_down.py {ids} --yes"
              if not all_pods else
              "  실제 종료하려면:  python cloud/runpod/runpod_down.py --all --yes")
        return []

    deleted = []
    for p in targets:
        pid = str(p.get("id"))
        delete(pid)
        print(f"[runpod_down] 삭제됨: {pid}")
        deleted.append(pid)
    return deleted


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("pod_id", nargs="?", default=None)
    p.add_argument("--all", dest="all_pods", action="store_true", help="전체 파드 종료")
    p.add_argument("--yes", action="store_true",
                   help="확인 없이 실제 삭제 (없으면 드라이런)")
    args = p.parse_args()
    run(pod_id=args.pod_id, all_pods=args.all_pods, yes=args.yes)


if __name__ == "__main__":
    _cli()
