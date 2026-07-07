"""학습 파드 한 번 훑기 — 수집·분류·#ai-리포팅 발송을 한 호출에 묶는다.

폴링 때 "확인(wandb_status)"과 "보고(ai_report)"가 따로라 보고를 자꾸 빼먹는 문제를
없앤다: 이 스크립트를 부르면 **수집→분류→채널 발송이 원자적으로** 일어난다(빼먹기 불가).
`poll.py --do` 의 학습단계 내용물로 쓰이며, 단독으로도 곁눈질용으로 부를 수 있다.

수집: wandb_status.run(step/loss/ETA/state) + runpod pod 상태 + (선택) HF 태그 업로드 여부.
분류(RUNPOD_OPS 리포팅 의무 = 시작·변화·완료·이상):
  - 순항   : 파드 RUNNING + run running + step 진전       → 정상 추세 한 줄
  - STALL  : 파드 RUNNING + step 이 지난 호출 대비 0 진전  → ⚠️ 이상(과금 중 hang 의심)
  - 완료   : 파드 GONE(404) + run finished                → 🎉 (+ HF 태그 확인)
  - 파드유실: 파드 GONE + run 이 finished 아님             → ❌ 이상(학습 미완 가능)
  - 실패   : run state ∈ {failed, crashed}                → ❌ 이상

상태파일(temp)에 지난 step 을 남겨 STALL(진전 0)을 감지한다 — 도배 스로틀이 아니라
"이상 즉시 알림" 의무를 기계화하려는 것(폴 간격=케이던스라 매번 보고해도 도배 아님).

전제: `.env` 의 `WANDB_API_KEY`(읽기 전용·비과금), `RUNPOD_API_KEY`, `AI_REPORTING_WEBHOOK_URL`.

  - CLI:  python cloud/train/train_watch.py --pod-id yx8gjr19fcpqlo --label "cubeinbowl v2-s15000 1계단"
          python cloud/train/train_watch.py --pod-id X --hf-repo adwel94/gr00t-cubeinbowl --expect-tag v2-s15000
          python cloud/train/train_watch.py --run-id kuusp3ba --no-report   # 채널 발송 없이 곁눈질만
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "cloud" / "common"))   # ai_report, utils.discord
sys.path.insert(0, str(_ROOT / "cloud" / "runpod"))   # runpod_client

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.env_config import load_env  # noqa: E402
import wandb_status  # noqa: E402  (같은 디렉토리)
import ai_report      # noqa: E402  (cloud/common)

# STALL 판정: 파드 RUNNING 인데 step 이 이 시간(초) 넘게 안 움직이면 이상.
_STALL_SECONDS = 900   # 15분 — 학습 폴 간격(~20분)보다 짧게 둬 한 번 걸러도 잡힌다.


def _state_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return Path(tempfile.gettempdir()) / f"train_watch_{safe}.json"


def _update_state(name: str, step, now: float):
    """지난 호출의 step 을 읽어 (진전량, 무진전 지속초)를 돌려주고 현재 step 을 저장한다.

    step 이 바뀌면 last_changed 를 갱신, 안 바뀌면 유지 → now - last_changed 로 정체 지속을 잰다.
    """
    p = _state_path(name)
    prev = None
    if p.exists():
        try:
            prev = json.loads(p.read_text())
        except Exception:
            prev = None
    delta = None
    stalled_secs = 0.0
    last_changed = now
    if prev and prev.get("step") is not None and step is not None:
        delta = step - prev["step"]
        if delta == 0:
            last_changed = prev.get("last_changed", prev.get("ts", now))
            stalled_secs = now - last_changed
        # delta>0 이면 방금 움직임 → last_changed=now(위 기본값)
    try:
        p.write_text(json.dumps({"step": step, "ts": now, "last_changed": last_changed}))
    except Exception:
        pass
    return delta, stalled_secs


def _pod_state(pod_id: str | None) -> dict:
    """{'alive': bool, 'status': str, 'cost': float|None}. pod_id 없으면 alive=None(모름)."""
    if not pod_id:
        return {"alive": None, "status": "?", "cost": None}
    try:
        from runpod_client import pod
        p = pod(pod_id)
        return {"alive": True, "status": p.get("desiredStatus", "?"), "cost": p.get("costPerHr")}
    except Exception as e:
        # 404 = 자가종료(정상 완료 또는 실패 종료) — 여기선 '사라짐'만 알린다.
        if "404" in str(e) or "not found" in str(e).lower():
            return {"alive": False, "status": "GONE(404)", "cost": None}
        return {"alive": None, "status": f"조회실패({type(e).__name__})", "cost": None}


def _hf_has_tag(repo: str | None, tag: str | None):
    """(uploaded_tag, has_ckpt) 또는 (None,None) — repo/tag 미지정 시 확인 안 함."""
    if not (repo and tag):
        return None, None
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=os.getenv("HF_TOKEN"))
        refs = api.list_repo_refs(repo)
        tags = {t.name for t in refs.tags}
        branches = {b.name for b in refs.branches}
        return (tag in tags), ("ckpt-latest" in branches)
    except Exception:
        return None, None


def _fmt_pct(step, total):
    return f"{(step / total * 100):.0f}%" if (step and total) else "?"


def _classify(wb: dict, pod: dict, uploaded, has_ckpt, delta, stalled_secs, label: str):
    """(severity, message) 반환. severity ∈ {'done','anomaly','normal','init'}."""
    tag = label or wb.get("name") or "학습"
    state = wb.get("state")
    step, total = wb.get("step"), wb.get("total")
    loss = wb.get("loss")
    eta_s = wb.get("eta_s")
    sps = wb.get("s_per_step")
    pct = _fmt_pct(step, total)
    eta = f"ETA ~{eta_s/60:.0f}분" if eta_s else "ETA 미정"
    lossf = f"loss {loss:.3f}" if isinstance(loss, (int, float)) else "loss ?"
    spsf = f"{sps:.2f}s/step" if sps else ""

    # 완료 / 파드유실 (파드가 사라진 경우)
    if pod.get("alive") is False:
        if state == "finished":
            up = ""
            if uploaded is True:
                up = f" HF 태그 업로드 ✓{' + ckpt-latest ✓' if has_ckpt else ''}"
            elif uploaded is False:
                up = " ⚠️ HF 태그 아직 미확인(업로드 중일 수 있음)"
            return "done", f"🎉 [{tag}] 완료 — step {step}/{total}, {lossf}. 파드 자가종료(과금 클린).{up}"
        return "anomaly", (f"❌ [{tag}] 파드 유실 — run state={state}, step {step}/{total}({pct}) 에서 "
                           f"파드 404. 학습 미완 가능 — W&B/로그 확인 필요. {wb.get('url','')}")

    # run 자체가 실패
    if state in ("failed", "crashed"):
        return "anomaly", (f"❌ [{tag}] 학습 run {state} — step {step}/{total}({pct}), {lossf}. "
                           f"확인 필요. {wb.get('url','')}")

    # 파드 RUNNING (또는 상태 모름) — 진행 중
    cost = f", {pod['cost']}/hr" if pod.get("cost") else ""
    if step is None:
        return "init", f"⏳ [{tag}] 초기화 중 — 부팅/데이터 로딩(아직 step 기록 전). 파드 {pod['status']}{cost}."
    if stalled_secs >= _STALL_SECONDS:
        return "anomaly", (f"⚠️ [{tag}] STALL 의심 — step {step} 에서 {stalled_secs/60:.0f}분째 진전 0. "
                           f"파드 {pod['status']}{cost}(과금 중). hang 여부 확인 필요. {wb.get('url','')}")
    dcol = f" (+{delta} since last)" if delta else ""
    return "normal", f"📈 [{tag}] 순항 — step {step}/{total}({pct}){dcol}, {lossf}, {spsf}, {eta}. 파드 {pod['status']}{cost}."


def _next_hint(severity: str) -> str:
    return {
        "done": "▶ 다음: 서빙(gr00t_serve)+홀드아웃 평가 → 성공률 확인 → decide.",
        "anomaly": "▶ 다음: 원인 확인 후 사람 판단 요청(과금 중이면 runpod_down 고려).",
        "init": "▶ 다음: 다음 폴에서 uv sync/데이터셋/학습 진입 관문 확인.",
        "normal": "▶ 다음: 다음 폴 예약(≤20분). 완료/이상이면 그때 단계 전이.",
    }.get(severity, "")


def run(
    pod_id: str | None = None,
    run_id: str | None = None,
    hf_repo: str | None = None,
    expect_tag: str | None = None,
    label: str | None = None,
    report: bool = True,
) -> dict:
    """학습 상태를 한 번 훑어 dict 반환. report=True 면 #ai-리포팅 에 분류된 한 줄을 발송."""
    load_env()
    now = time.time()
    wb = wandb_status.run(pod_id=pod_id, run_id=run_id)   # 사람용 글랜스 표를 먼저 출력
    pod = _pod_state(pod_id)
    uploaded, has_ckpt = _hf_has_tag(hf_repo, expect_tag)
    delta, stalled_secs = _update_state(wb.get("name") or (pod_id or "run"), wb.get("step"), now)
    severity, message = _classify(wb, pod, uploaded, has_ckpt, delta, stalled_secs, label)

    sent = False
    if report:
        try:
            ai_report.run(message)
            sent = True
        except SystemExit as e:      # 웹훅 미설정 등 — 발송 실패해도 곁눈질은 유효
            print(f"[train_watch] 채널 발송 skip: {e}")

    print("\n" + message)
    if not sent and report:
        print("[train_watch] (위 메시지 채널 미발송)")
    print(_next_hint(severity))
    return {"severity": severity, "message": message, "sent": sent,
            "pod": pod, "wandb": wb, "delta": delta, "stalled_secs": stalled_secs}


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pod-id", default=None, help="run 이름 gr00t-ft-<pod_id> 로 조회 + 파드 상태")
    p.add_argument("--run-id", default=None, help="W&B run id 직접 지정")
    p.add_argument("--hf-repo", default=None, help="완료 시 태그 업로드 확인할 HF repo")
    p.add_argument("--expect-tag", default=None, help="확인할 모델 태그 (예: v2-s15000)")
    p.add_argument("--label", default=None, help="리포트에 쓸 사람용 라벨 (예: 'cubeinbowl v2-s15000 1계단')")
    p.add_argument("--no-report", dest="report", action="store_false", help="채널 발송 없이 곁눈질만")
    args = p.parse_args()
    run(pod_id=args.pod_id, run_id=args.run_id, hf_repo=args.hf_repo,
        expect_tag=args.expect_tag, label=args.label, report=args.report)


if __name__ == "__main__":
    _cli()
