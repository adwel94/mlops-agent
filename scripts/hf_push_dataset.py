"""LeRobot 데이터셋 디렉토리를 HuggingFace Hub 로 push + 검증 (④ 클라우드 흐름).

`h5_to_lerobot` 출력(data/datasets/<task>/lerobot/)을 HF dataset repo 로 올리고,
올라간 결과를 다시 조회해 **구조·카운트가 맞는지 확인**한다. 파드는 부팅 때
`fetch_dataset.sh` 가 이걸 다시 받는다(직접 전송 없이 HF 가 단일 출처).

토큰: 프로젝트 루트 .env 의 HF_TOKEN (write 권한). public repo 면 pull 엔 토큰 불필요.

  - Python:  from scripts.hf_push_dataset import run, verify
             run("data/datasets/ThreeColoredCubes-v1/lerobot",
                 "adwel94/maniskill-threecubes-lerobot")
             verify("adwel94/maniskill-threecubes-lerobot")   # 업로드 없이 확인만
  - CLI:     python scripts/hf_push_dataset.py \
                 data/datasets/ThreeColoredCubes-v1/lerobot \
                 adwel94/maniskill-threecubes-lerobot
             python scripts/hf_push_dataset.py - <repo_id> --verify-only
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.env_config import load_env  # noqa: E402

try:  # Windows 콘솔 기본 cp949 에서 유니코드(em-dash 등) 출력 깨짐 방지
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# LeRobot v2.1 가 요구하는 meta 파일 (로더가 존재를 가정).
_REQUIRED_META = ("info.json", "episodes.jsonl", "tasks.jsonl", "modality.json", "stats.json")


def verify(repo_id: str, repo_type: str = "dataset") -> dict:
    """HF repo 의 LeRobot 구조·카운트를 조회해 점검. 결과 dict 반환, 불일치면 RuntimeError.

    체크: ① 필수 meta 파일 존재 ② parquet 수 == info.total_episodes
          ③ mp4 수 == info.total_videos ④ tasks.jsonl 행 수 == info.total_tasks.
    """
    load_env()
    token = os.getenv("HF_TOKEN")
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi(token=token)
    files = api.list_repo_files(repo_id, repo_type=repo_type)

    meta_files = {f.split("/")[-1] for f in files if f.startswith("meta/")}
    parquet = [f for f in files if f.endswith(".parquet")]
    mp4 = [f for f in files if f.endswith(".mp4")]

    missing = [m for m in _REQUIRED_META if m not in meta_files]

    # info.json 다운로드해 선언된 카운트와 대조.
    info = {}
    if "info.json" in meta_files:
        p = hf_hub_download(repo_id, "meta/info.json", repo_type=repo_type, token=token)
        info = json.loads(Path(p).read_text(encoding="utf-8"))

    n_tasks = 0
    if "tasks.jsonl" in meta_files:
        p = hf_hub_download(repo_id, "meta/tasks.jsonl", repo_type=repo_type, token=token)
        n_tasks = sum(1 for ln in Path(p).read_text(encoding="utf-8").splitlines() if ln.strip())

    exp_eps = info.get("total_episodes")
    exp_vids = info.get("total_videos")
    exp_tasks = info.get("total_tasks")

    checks = [
        ("meta 파일 완비", not missing, f"누락: {missing}" if missing else "info/episodes/tasks/modality/stats"),
        ("parquet 수 == total_episodes", exp_eps is None or len(parquet) == exp_eps,
         f"{len(parquet)} vs {exp_eps}"),
        ("mp4 수 == total_videos", exp_vids is None or len(mp4) == exp_vids,
         f"{len(mp4)} vs {exp_vids}"),
        ("tasks 행 수 == total_tasks", exp_tasks is None or n_tasks == exp_tasks,
         f"{n_tasks} vs {exp_tasks}"),
    ]

    url = f"https://huggingface.co/datasets/{repo_id}"
    print(f"[verify] {url}")
    print(f"  codebase_version={info.get('codebase_version')}  fps={info.get('fps')}  "
          f"total_frames={info.get('total_frames')}")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'OK ' if ok else 'FAIL'}] {name}  ({detail})")
        all_ok = all_ok and ok

    result = {
        "repo_id": repo_id, "url": url, "ok": all_ok,
        "n_parquet": len(parquet), "n_mp4": len(mp4), "n_tasks": n_tasks,
        "info": info, "missing_meta": missing,
    }
    if not all_ok:
        raise RuntimeError(f"검증 실패 — HF 데이터셋 구조 불일치: {repo_id}")
    print("[verify] PASS — 데이터셋이 학습 파드에서 받을 준비 완료.")
    return result


def run(
    local_dir: str,
    repo_id: str,
    private: bool = False,
    repo_type: str = "dataset",
    commit_message: str = "upload lerobot dataset",
    verify_only: bool = False,
    version: str | None = None,
    task: str | None = None,
) -> str:
    """local_dir 을 HF repo_id 로 업로드하고 검증한 뒤 repo URL 을 반환.

    verify_only=True 면 업로드를 건너뛰고 기존 repo 만 점검한다(local_dir 무시).

    version 을 주면(예: "v1") 업로드+검증 성공 직후 그 이름의 **불변 git 태그**를 repo 에
    박고 MANIFEST.yaml 에 한 줄 기록한다. 같은 태그가 이미 있으면 = 버전 충돌 →
    에러(데이터가 바뀌었으면 새 번호를 쓰라는 신호; 태그는 덮어쓰지 않는다).
    """
    if verify_only:
        return verify(repo_id, repo_type=repo_type)["url"]

    load_env()  # .env -> HF_TOKEN
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN 미설정 — .env 에 write 토큰을 넣으세요.")

    path = Path(local_dir).resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"디렉토리 없음: {path}")

    from huggingface_hub import HfApi

    api = HfApi(token=token)

    # 버전 태그를 박을 거면 업로드 *전에* 충돌부터 막는다 (불변 원칙 — 새 commit 올리고
    # 나서 태그 막히면 main 만 더럽혀짐). 같은 버전 = 데이터가 같아야 함; 바뀌었으면 새 번호.
    if version:
        refs = api.list_repo_refs(repo_id, repo_type=repo_type)
        if version in {t.name for t in refs.tags}:
            raise RuntimeError(
                f"태그 '{version}' 이 이미 {repo_id} 에 존재 — 버전은 불변입니다. "
                f"데이터가 바뀌었으면 새 버전 번호를 쓰세요(예: 다음 vN)."
            )

    api.create_repo(repo_id, repo_type=repo_type, private=private, exist_ok=True)
    print(f"[hf_push] repo={repo_id} (private={private}) <- {path}")
    api.upload_folder(
        repo_id=repo_id,
        repo_type=repo_type,
        folder_path=str(path),
        commit_message=commit_message,
    )
    url = f"https://huggingface.co/datasets/{repo_id}"
    print(f"[hf_push] upload done -> {url}")
    result = verify(repo_id, repo_type=repo_type)  # 업로드 직후 무결성 확인

    if version:
        api.create_tag(repo_id, tag=version, repo_type=repo_type)
        print(f"[hf_push] tagged {repo_id}@{version}")
        from scripts.manifest import add_dataset, slug_from_repo
        add_dataset(
            task or slug_from_repo(repo_id), version,
            episodes=result.get("info", {}).get("total_episodes"),
            repo=repo_id, tag=version,
        )
    return url


def _cli() -> None:
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("local_dir", help="LeRobot 데이터셋 디렉토리 (lerobot/). --verify-only 면 '-' 가능")
    p.add_argument("repo_id", help="HF repo id, 예: adwel94/maniskill-threecubes-lerobot")
    p.add_argument("--private", action="store_true", help="private repo (기본: public)")
    p.add_argument("--repo-type", default="dataset")
    p.add_argument("--message", default="upload lerobot dataset")
    p.add_argument("--verify-only", action="store_true", help="업로드 없이 기존 repo 만 점검")
    p.add_argument("--version", default=None,
                   help="불변 버전 태그 (예: v1) — 박고 MANIFEST.yaml 에 기록. 중복이면 에러")
    p.add_argument("--task", default=None,
                   help="MANIFEST 태스크 키 (기본: repo 이름에서 slug 추출)")
    args = p.parse_args()
    run(args.local_dir, args.repo_id, private=args.private,
        repo_type=args.repo_type, commit_message=args.message,
        verify_only=args.verify_only, version=args.version, task=args.task)


if __name__ == "__main__":
    _cli()
