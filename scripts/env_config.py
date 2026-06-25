"""프로젝트 비밀키/설정 로더 — `.env` (프로젝트 루트, gitignore) 를 os.environ 으로.

의존성 없음(`python-dotenv` 불필요). 엔트리포인트 시작 시 `load_env()` 를 호출하면
`.env` 의 `KEY=VALUE` 들이 환경변수로 올라온다. **이미 셸에 export 된 값은 덮어쓰지
않는다**(셸 우선) — CI/임시 오버라이드가 .env 보다 강함.

지금 쓰는 곳: RunPod 스킬(runpod_up/ls/down) 이 RUNPOD_API_KEY 를 읽기 전에 호출.
앞으로(학습 파이프라인): W&B / Discord / Prefect / HF 토큰 등도 같은 .env 한 곳에서.

  - 로드:    from scripts.env_config import load_env; load_env()
  - 필수값:  from scripts.env_config import require; key = require("RUNPOD_API_KEY")
"""
from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_loaded: set[str] = set()   # 같은 파일 중복 파싱 방지


def _parse(path: Path) -> dict[str, str]:
    """아주 단순한 .env 파서: `KEY=VALUE`, `# 주석`, 빈 줄, 선택적 `export ` 접두사,
    값 양끝의 따옴표 제거. 보간(${...})은 지원하지 않음 (필요해지면 그때)."""
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def load_env(path: str | os.PathLike | None = None, override: bool = False) -> dict[str, str]:
    """`.env` 를 읽어 os.environ 에 반영. 반영한 {key: value} 를 반환.

    path 미지정 시 프로젝트 루트의 `.env`. 파일이 없으면 조용히 no-op(셸 export 만으로도
    동작하도록). override=False(기본) 면 이미 설정된 환경변수는 건드리지 않는다.
    """
    p = Path(path) if path else _PROJECT_ROOT / ".env"
    if not p.exists():
        return {}
    key = str(p.resolve())
    if key in _loaded and not override:
        return {}
    _loaded.add(key)

    applied: dict[str, str] = {}
    for k, v in _parse(p).items():
        if v == "":          # 빈 플레이스홀더(KEY=)는 미설정으로 취급
            continue
        if override or k not in os.environ:
            os.environ[k] = v
            applied[k] = v
    return applied


def require(name: str) -> str:
    """`load_env()` 후 환경변수 하나를 꺼내 반환. 없으면 명확한 에러."""
    load_env()
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"{name} 가 설정되지 않았습니다. 프로젝트 루트 .env 에 `{name}=...` 를 넣거나 "
            f"셸에서 export 하세요. (템플릿: .env.example)"
        )
    return val


if __name__ == "__main__":
    # 진단: 어떤 키가 .env 에서 올라오는지 (값은 마스킹).
    applied = load_env(override=True)
    if not applied:
        print(f"[env_config] .env 없음 또는 비어있음 ({_PROJECT_ROOT / '.env'})")
    else:
        for k in applied:
            v = os.environ[k]
            masked = (v[:4] + "…" + v[-2:]) if len(v) > 8 else "***"
            print(f"[env_config] {k} = {masked}")
