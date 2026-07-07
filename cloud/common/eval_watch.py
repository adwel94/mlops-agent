"""평가 진행 한 번 훑기 — eval_diag.jsonl 을 읽어 진행률·성공률·실패사유를 #ai-리포팅에.

train_watch 의 평가판. `gr00t_eval` 은 에피소드마다 진단 레코드를 `<dataset>.eval_diag.jsonl`
로 증분 flush 한다(kill 나도 부분결과 생존). 이 스크립트는 그 파일을 읽어 **진행률 + 러닝
성공률 + 실패사유 분해**를 한 줄로 만들어 채널에 발송한다 — 확인·보고를 원자화(빼먹기 방지).
`poll.py --do` 의 평가단계 내용물로 쓰인다.

실패사유는 각 레코드의 `reason` 라벨(env.classify_outcome 이 남긴 것)을 그대로 센다 —
eval_watch 는 라벨 뜻을 모른다(태스크별 코드 없음, CLAUDE.md 규칙 1). 어느 라벨이 성공인지
모르므로 실패 집계는 success=False 레코드만 대상(범용). 큐브 태스크면 못집음/틀린색/미완 이
뜨고, 다른 태스크는 자기 env 가 선언한 사유가 뜬다. success_rate·ik_fails 는 범용 신호로 병기.
(reason 없는 옛 파일은 "실패"로 폴백 — 성공률은 그대로 보인다.)

상태파일(temp)에 지난 done 수를 남겨 STALL(진전 0 = eval hang / 서버 불통)을 감지 →
"이상 즉시" 의무 기계화. 폴 간격=케이던스(≤10분)라 매 폴 발송해도 도배 아님.

전제: `.env` 의 `AI_REPORTING_WEBHOOK_URL`. (읽기 전용·비과금 — 로컬 jsonl 만 읽는다.)

  - CLI:  python cloud/common/eval_watch.py --diag data/.../holdout.rgb....eval_diag.jsonl \
              --total 50 --label "cubeinbowl v2-s15000 홀드아웃"
          python cloud/common/eval_watch.py --traj-path data/.../holdout.rgb....h5 --total 50   # 경로에서 diag 유추
          python cloud/common/eval_watch.py --diag <p> --total 50 --no-report                   # 곁눈질만
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_HERE))   # ai_report, utils.discord

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import ai_report  # noqa: E402

# STALL: done 이 이 시간(초) 넘게 안 늘면 이상(평가 hang / 서버 불통). 폴 간격(~10분)보다 짧게.
_STALL_SECONDS = 480   # 8분


def _diag_from_traj(traj_path: str) -> Path:
    p = Path(traj_path)
    return p.parent / (p.stem + ".eval_diag.jsonl")


def _read_records(diag: Path) -> list[dict]:
    """증분 flush 되는 jsonl 을 안전하게 읽는다 — 마지막 줄이 반쯤 쓰였으면 건너뛴다."""
    recs = []
    if not diag.exists():
        return recs
    for line in diag.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            continue   # 아직 flush 안 끝난 마지막 줄 — 다음 폴에서 잡힌다
    return recs


def _tally(recs: list[dict]) -> dict:
    """진행/성공률(범용) + 실패사유 집계(env 선언 라벨을 뜻 모른 채 그대로 센다).

    실패 사유는 각 레코드의 `reason`(env.classify_outcome 이 남긴 라벨)을 센다 — eval_watch 는
    "못집음"이 뭔지 모른다(태스크별 코드 없음, CLAUDE.md 규칙 1). 어느 라벨이 성공인지도
    모르므로 실패 집계는 success=False 레코드만 대상으로 한다(=범용). reason 없는 옛 파일은
    "실패"로 폴백. success_rate·ik_fails 는 어느 태스크든 통하는 범용 신호.
    """
    from collections import Counter
    done = len(recs)
    succ = sum(1 for r in recs if r.get("success"))
    ik_fails = sum(int(r.get("ik_fails") or 0) for r in recs)
    fail_reasons = Counter((r.get("reason") or "실패") for r in recs if not r.get("success"))
    return {
        "done": done, "success": succ,
        "rate": (succ / done) if done else 0.0,
        "ik_fails": ik_fails, "fail_reasons": fail_reasons,
    }


def _state_path(key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return Path(tempfile.gettempdir()) / f"eval_watch_{safe}.json"


def _stall(key: str, done: int, now: float) -> float:
    """지난 done 과 비교해 무진전 지속(초)을 돌려주고 현재를 저장."""
    p = _state_path(key)
    prev = None
    if p.exists():
        try:
            prev = json.loads(p.read_text())
        except Exception:
            prev = None
    last_changed = now
    stalled = 0.0
    if prev and prev.get("done") is not None:
        if done == prev["done"]:
            last_changed = prev.get("last_changed", prev.get("ts", now))
            stalled = now - last_changed
    try:
        p.write_text(json.dumps({"done": done, "ts": now, "last_changed": last_changed}))
    except Exception:
        pass
    return stalled


def _classify(t: dict, total: int | None, stalled: float, label: str):
    tag = label or "평가"
    done = t["done"]
    pct = f"{done/total*100:.0f}%" if total else "?"
    nfail = done - t["success"]
    # env 가 선언한 실패 라벨을 많은 순으로 — eval_watch 는 라벨 뜻을 모른다(범용).
    breakdown = ", ".join(f"{lab} {c}" for lab, c in t["fail_reasons"].most_common()) or "없음"
    body = (f"평가 {done}/{total or '?'}({pct}) — 성공 {t['success']}/{done} "
            f"({t['rate']:.2f}). 실패 {nfail}: {breakdown}. ik_fails 합 {t['ik_fails']}.")

    if done == 0:
        return "init", f"⏳ [{tag}] {body} (아직 첫 에피소드 전 — 서버 붙는 중일 수 있음)"
    if total and done >= total:
        return "done", f"✅ [{tag}] 최종 — {body}"
    if stalled >= _STALL_SECONDS:
        return "anomaly", (f"⚠️ [{tag}] STALL 의심 — {done}개에서 {stalled/60:.0f}분째 진전 0 "
                           f"(eval hang / 서버 불통?). {body}")
    return "normal", f"📊 [{tag}] {body}"


def _next_hint(sev: str) -> str:
    return {
        "done": "▶ 다음: 성공률로 decide(2계단 갈지) + MANIFEST set-eval(홀드아웃=v2) + 서빙 파드 runpod_down.",
        "anomaly": "▶ 다음: 서버/파드 상태 확인(runpod_ls) → 필요시 재시작 또는 사람 판단.",
        "init": "▶ 다음: 다음 폴에서 첫 에피소드 기록되는지 확인(안 되면 서버 연결 점검).",
        "normal": "▶ 다음: 다음 폴 예약(≤10분). done==total 이면 최종 판정.",
    }.get(sev, "")


def run(
    diag: str | Path | None = None,
    traj_path: str | None = None,
    total: int | None = None,
    label: str | None = None,
    report: bool = True,
) -> dict:
    """eval_diag.jsonl 을 읽어 진행/성공률/실패사유를 dict 반환. report=True 면 #ai-리포팅 발송."""
    if diag is None:
        if not traj_path:
            raise SystemExit("[eval_watch] --diag 또는 --traj-path 중 하나 필요.")
        diag = _diag_from_traj(traj_path)
    diag = Path(diag)
    now = time.time()
    recs = _read_records(diag)
    t = _tally(recs)
    stalled = _stall(str(diag), t["done"], now)
    sev, message = _classify(t, total, stalled, label or diag.stem)

    # 사람용 글랜스
    reasons_glance = " ".join(f"{lab}={c}" for lab, c in t["fail_reasons"].most_common()) or "-"
    print(f"[eval_watch] {diag.name}: done={t['done']}/{total or '?'} "
          f"success={t['success']} rate={t['rate']:.3f} ik_fails={t['ik_fails']} "
          f"| 실패사유 {reasons_glance}")

    sent = False
    if report:
        try:
            ai_report.run(message)
            sent = True
        except SystemExit as e:
            print(f"[eval_watch] 채널 발송 skip: {e}")

    print("\n" + message)
    if report and not sent:
        print("[eval_watch] (위 메시지 채널 미발송)")
    print(_next_hint(sev))
    return {"severity": sev, "message": message, "sent": sent, "tally": t, "stalled_s": stalled}


def _cli() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--diag", default=None, help="eval_diag.jsonl 경로")
    p.add_argument("--traj-path", default=None, help="대신 소스 h5 경로 (여기서 diag 유추)")
    p.add_argument("--total", type=int, default=None, help="전체 에피소드 수(진행률·완료 판정용)")
    p.add_argument("--label", default=None, help="리포트 라벨 (예: 'cubeinbowl v2-s15000 홀드아웃')")
    p.add_argument("--no-report", dest="report", action="store_false", help="채널 발송 없이 곁눈질만")
    args = p.parse_args()
    run(diag=args.diag, traj_path=args.traj_path, total=args.total,
        label=args.label, report=args.report)


if __name__ == "__main__":
    _cli()
