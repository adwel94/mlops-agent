"""MANIFEST.yaml 원장 읽기/쓰기 — 데이터셋·모델 HF 버전의 단일 출처.

컨벤션: **태스크당 repo 하나 + git 태그로 버전**. 큰 데이터는 HF(태그)에, 로컬엔
최신 작업본만, 이 원장이 "어떤 버전이 어디 있나"를 잇는 지도. 둘이 자동으로 채운다:

  - `hf_push_dataset.py --version vN`  → add_dataset (업로드+태그 성공 직후)
  - `cloud/train/launch_train.py`      → add_model (런치 시 eval=null 로; 평가 후 수동 기록)

태스크 키(top-level)는 데이터셋 repo 이름에서 뽑은 **slug** (`maniskill-<slug>-lerobot`
→ `<slug>`) — push/train 양쪽이 같은 dataset repo 를 알고 있어 키가 일치한다.

  - Python:  from scripts.manifest import add_dataset, add_model, slug_from_repo
  - CLI:     python scripts/manifest.py show
             python scripts/manifest.py set-eval <task> <model_name> <value>
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = _ROOT / "MANIFEST.yaml"

_HEADER = (
    "# MANIFEST — 데이터셋·모델 버전 원장 (HF 버전의 단일 출처).\n"
    "# 컨벤션: 태스크당 repo 하나 + git 태그로 버전. 큰 데이터는 HF 태그에, 로컬엔 최신\n"
    "# 작업본만, 이 파일이 둘을 잇는 지도. 태그는 불변 — 데이터/설정이 바뀌면 새 버전\n"
    "# 번호를 쓴다(같은 태그에 덮어쓰지 않음).\n"
    "# 자동 append: hf_push_dataset.py(데이터셋) / launch_train.py(모델, eval=null 로 시작).\n"
    "# 모델 eval 은 gr00t_eval 후 기록: python scripts/manifest.py set-eval <task> <model> <값>\n"
)


def slug_from_repo(repo: str) -> str:
    """`adwel94/maniskill-threecubes-lerobot` → `threecubes` (manifest 태스크 키)."""
    name = repo.split("/")[-1]
    for pre in ("maniskill-",):
        if name.startswith(pre):
            name = name[len(pre):]
    for suf in ("-lerobot",):
        if name.endswith(suf):
            name = name[: -len(suf)]
    return name


def _today() -> str:
    return datetime.date.today().isoformat()


def load() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    return data or {}


def _save(data: dict) -> None:
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    MANIFEST_PATH.write_text(_HEADER + body, encoding="utf-8")


def add_dataset(task: str, version: str, *, episodes: int | None, repo: str,
                tag: str | None, date: str | None = None) -> None:
    """데이터셋 버전 한 줄 기록 (upsert)."""
    data = load()
    node = data.setdefault(task, {}).setdefault("datasets", {})
    node[version] = {
        "episodes": episodes,
        "repo": repo,
        "tag": tag,
        "date": date or _today(),
    }
    _save(data)
    print(f"[manifest] datasets/{task}/{version} 기록 -> {MANIFEST_PATH.name}")


def add_model(task: str, name: str, *, dataset: str, steps: int, full: bool, repo: str,
              tag: str | None, eval: float | None = None, date: str | None = None,
              image: str | None = None) -> None:
    """모델 학습런 한 줄 기록 (upsert). eval 은 평가 후 set-eval 로 채움.

    image = 학습에 쓴 학습 이미지 레퍼런스(불변 추적용, 예 maniskill-gr00t-train:git-<sha>).
    선택 필드 — 옛 항목엔 없을 수 있고(하위호환), 주어질 때만 기록한다.
    """
    data = load()
    node = data.setdefault(task, {}).setdefault("models", {})
    entry = {
        "dataset": dataset,
        "steps": steps,
        "full": full,
        "repo": repo,
        "tag": tag,
        "eval": eval,
        "date": date or _today(),
    }
    if image:                       # 선택 필드 — 없으면 옛 스키마 그대로(키 자체를 안 만듦)
        entry["image"] = image
    node[name] = entry
    _save(data)
    print(f"[manifest] models/{task}/{name} 기록 -> {MANIFEST_PATH.name}")


def set_eval(task: str, name: str, value: float, method: str = "v2") -> None:
    """기존 모델 항목의 eval 값을 채운다 (gr00t_eval 결과 기록).

    method = 평가 방식. v2 = 홀드아웃 씬(학습 안 쓴 seed, 배포 근사; 현행 기본).
    v1 = 학습 씬 측정(낙관 편향, 옛 값). v1↔v2 는 사과-오렌지라 직접 비교 금지.
    """
    data = load()
    try:
        entry = data[task]["models"][name]
    except KeyError:
        raise SystemExit(f"항목 없음: models/{task}/{name} — manifest 에 먼저 기록돼 있어야 합니다.")
    entry["eval"] = value
    entry["eval_method"] = method
    _save(data)
    print(f"[manifest] models/{task}/{name}.eval = {value} (eval_method={method})")


def _cli() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="MANIFEST.yaml 전체 출력")
    se = sub.add_parser("set-eval", help="모델 항목 eval 값 기록")
    se.add_argument("task")
    se.add_argument("model_name")
    se.add_argument("value", type=float)
    se.add_argument("--method", default="v2", choices=["v1", "v2"],
                    help="평가 방식 (기본 v2=홀드아웃; v1=학습 씬 옛 방식)")
    args = p.parse_args()

    if args.cmd == "show":
        if MANIFEST_PATH.exists():
            print(MANIFEST_PATH.read_text(encoding="utf-8"))
        else:
            print("(MANIFEST.yaml 없음)")
    elif args.cmd == "set-eval":
        set_eval(args.task, args.model_name, args.value, args.method)


if __name__ == "__main__":
    _cli()
