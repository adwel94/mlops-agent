"""W&B run 의 스칼라 메트릭을 끌어와 학습 진행 글랜스를 출력 (에이전트 모니터링).

`read_logs.py` 의 트윈 — 그쪽이 raw stdout 이라면 이쪽은 **loss/lr/grad_norm/step + ETA**.
파드가 W&B 로 푸시한 run(`gr00t-ft-<pod_id>`)을 공개 API 로 읽어 한 표로 보여준다.
도중에 곁눈질하는 휘발성 글랜스이지 산출물이 아니다(분석 리포트는 별도 스킬의 몫).

run 지정 우선순위: --run-id > --pod-id(이름 `gr00t-ft-<pod_id>`) > 프로젝트 최신 run.
throughput 은 최근 history 구간의 (Δ_runtime / Δstep) 로 추정해 ETA 를 낸다.

전제: `.env` 의 `WANDB_API_KEY`. `wandb` 패키지(공개 API 용, 읽기 전용·비과금).

  - CLI:  python cloud/train/wandb_status.py                 # 프로젝트 최신 run
          python cloud/train/wandb_status.py --pod-id 4sf6ijah4wotep
          python cloud/train/wandb_status.py --run-id hodv562y
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

_RECENT = 50  # throughput 추정에 쓸 최근 history 포인트 수


def _fmt_dur(seconds: float) -> str:
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _resolve_run(api, *, run_id, pod_id, project, entity):
    """우선순위에 따라 wandb Run 객체를 찾는다."""
    entity = entity or os.getenv("WANDB_ENTITY") or api.default_entity
    project = project or os.getenv("WANDB_PROJECT") or "maniskill-gr00t"
    path = f"{entity}/{project}"
    if run_id:
        return api.run(f"{path}/{run_id}")
    if pod_id:
        name = f"gr00t-ft-{pod_id}"
        runs = api.runs(path, filters={"display_name": name})
        for r in runs:  # 이름 일치 첫 run
            return r
        raise RuntimeError(f"run '{name}' 을 {path} 에서 못 찾음 — pod_id 확인.")
    runs = api.runs(path, order="-created_at")
    for r in runs:  # 최신 run
        return r
    raise RuntimeError(f"{path} 에 run 이 하나도 없음.")


def run(
    pod_id: str | None = None,
    run_id: str | None = None,
    project: str | None = None,
    entity: str | None = None,
) -> dict:
    """run 메트릭을 dict 로 반환하고 사람용 표를 출력한다."""
    load_env()
    if not os.getenv("WANDB_API_KEY"):
        raise RuntimeError("WANDB_API_KEY 미설정 — .env 확인.")
    import wandb

    api = wandb.Api(timeout=30)
    r = _resolve_run(api, run_id=run_id, pod_id=pod_id, project=project, entity=entity)

    summary = dict(r.summary)
    cfg = dict(r.config)
    total = cfg.get("max_steps") or summary.get("train/total_steps")
    step = summary.get("train/global_step") or summary.get("_step")
    loss = summary.get("train/loss")
    lr = summary.get("train/learning_rate")
    gnorm = summary.get("train/grad_norm")
    runtime = summary.get("_runtime")

    # 최근 구간 throughput → ETA (running 일 때만 의미)
    sps = eta = None
    rows = [
        h for h in r.scan_history(keys=["train/global_step", "_runtime"])
        if h.get("train/global_step") is not None and h.get("_runtime") is not None
    ]
    if len(rows) >= 2:
        window = rows[-_RECENT:]
        g0, g1 = window[0]["train/global_step"], window[-1]["train/global_step"]
        t0, t1 = window[0]["_runtime"], window[-1]["_runtime"]
        if g1 > g0:
            sps = (t1 - t0) / (g1 - g0)
            if total and r.state == "running":
                eta = (total - g1) * sps

    info = {
        "name": r.name, "state": r.state, "url": r.url,
        "step": step, "total": total, "loss": loss, "lr": lr,
        "grad_norm": gnorm, "runtime": runtime, "s_per_step": sps, "eta_s": eta,
    }

    pct = f"{(step / total * 100):.1f}%" if (step and total) else "?"
    print(f"[wandb_status] {r.name}  ({r.state})")
    print(f"  step      : {step}/{total}  ({pct})")
    if loss is not None:
        print(f"  loss      : {loss:.4f}")
    if lr is not None:
        print(f"  lr        : {lr:.2e}")
    if gnorm is not None:
        print(f"  grad_norm : {gnorm:.3f}")
    if runtime is not None:
        print(f"  runtime   : {_fmt_dur(runtime)}")
    if sps is not None:
        line = f"  speed     : {sps:.2f} s/step"
        if eta is not None:
            line += f"  | ETA ~ {_fmt_dur(eta)} ({eta / 60:.0f} min) more"
        print(line)
    elif r.state == "running":
        print("  speed     : (아직 step 기록 부족 — init 중이거나 첫 로그 전)")
    print(f"  url       : {r.url}")
    return info


def _cli() -> None:
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pod-id", default=None, help="run 이름 gr00t-ft-<pod_id> 로 조회")
    p.add_argument("--run-id", default=None, help="W&B run id 직접 지정 (예: hodv562y)")
    p.add_argument("--project", default=None, help="W&B 프로젝트 (기본: WANDB_PROJECT 또는 maniskill-gr00t)")
    p.add_argument("--entity", default=None, help="W&B 엔티티 (기본: WANDB_ENTITY 또는 기본 엔티티)")
    args = p.parse_args()
    run(pod_id=args.pod_id, run_id=args.run_id, project=args.project, entity=args.entity)


if __name__ == "__main__":
    _cli()
