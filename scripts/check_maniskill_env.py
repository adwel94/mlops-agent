"""Health check + remediation for the ManiSkill harness environment.

Verifies the pieces every other skill depends on — core imports, CPU simulation,
the CPU render path, and (best-effort) the WSL mplib layer — and answers the one
question "can this harness run here?". But it doesn't stop at reporting: with
``--fix`` it repairs what it CAN by installing the pip layer from requirements.txt,
and what it can't do itself (create the conda env, provision WSL, set secrets) it
reports as concrete next steps pointing at SETUP.md.

requirements.txt is the single source for pip deps — this script *executes* it
(``pip install -r``), it does not restate versions. The WSL constants come from
task_to_h5 (their single source), not redeclared here.

(Dataset structure validation is intentionally NOT here — a produced HDF5 is
checked at generation time.)

Returns ``{"passed": bool, "checks": [...]}`` where each check has
``{"name", "level" (pass|warn|fail), "detail", "fix"}``; ``passed`` is True when
no check is at level "fail" (warns — e.g. WSL not set up — don't fail overall,
they only matter for the WSL-dependent skills).

Two interfaces:
  - Python:  from scripts.check_maniskill_env import run; run(fix=True)
  - CLI:     python scripts/check_maniskill_env.py [--fix] [--no-wsl]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# WSL constants live in task_to_h5 (single source) — import, don't redeclare.
try:
    from scripts.task_to_h5 import WSL_DISTRO, WSL_PYTHON
except ImportError:  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.task_to_h5 import WSL_DISTRO, WSL_PYTHON

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"

# Core imports every skill depends on (module name -> None; pip layer is installed
# wholesale from requirements.txt, so we only need to detect WHICH is missing).
CORE_IMPORTS = ["mani_skill", "sapien", "gymnasium", "h5py", "torch", "PIL"]
# Optional extras — only the LeRobot/report skills need these; missing = warn.
EXTRA_IMPORTS = ["pyarrow", "imageio"]

CheckResult = dict  # {"name": str, "level": str, "detail": str, "fix": str}


def _mk(name: str, level: str, detail: str = "", fix: str = "") -> CheckResult:
    return {"name": name, "level": level, "detail": detail, "fix": fix}


def _ok(name: str, detail: str = "") -> CheckResult:
    return _mk(name, "pass", detail)


def _warn(name: str, detail: str, fix: str = "") -> CheckResult:
    return _mk(name, "warn", detail, fix)


def _fail(name: str, detail: str, fix: str = "") -> CheckResult:
    return _mk(name, "fail", detail, fix)


def _missing(modules: list[str]) -> list[str]:
    out = []
    for m in modules:
        try:
            __import__(m)
        except Exception:
            out.append(m)
    return out


def _pip_install_requirements() -> int:
    """Install the pip layer from requirements.txt into THIS interpreter's env."""
    if not REQUIREMENTS.exists():
        print(f"[check] requirements.txt not found at {REQUIREMENTS} — cannot --fix.")
        return 1
    print(f"[check] pip install -r {REQUIREMENTS.name} (into {sys.executable}) ...")
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    ).returncode


def _check_wsl() -> CheckResult:
    """Best-effort probe of the WSL mplib layer (needed only for task_to_h5 /
    ee_verify / gr00t_eval). Not installable from here (Linux/apt/sudo) — on a
    miss we point at SETUP.md's WSL section rather than trying to fix it."""
    wsl_fix = "SETUP.md 'WSL' 절 참고 (mplib · mesa-vulkan) — task_to_h5·ee_verify·gr00t_eval 에만 필요"
    try:
        p = subprocess.run(
            ["wsl.exe", "-d", WSL_DISTRO, "--", WSL_PYTHON, "-c", "import mplib"],
            capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError:
        return _warn("wsl_mplib", "wsl.exe not found — WSL not installed", wsl_fix)
    except Exception as e:  # timeout, etc.
        return _warn("wsl_mplib", f"probe failed: {e!r}", wsl_fix)
    if p.returncode == 0:
        return _ok("wsl_mplib", f"{WSL_DISTRO}: import mplib OK")
    return _warn("wsl_mplib", f"{WSL_DISTRO}: import mplib failed", wsl_fix)


def _check_ik_backend() -> CheckResult:
    """IK 백엔드 프로브 (ee_verify·gr00t_eval 용). Windows 는 WSL 의 mplib 를,
    macOS/Linux 네이티브는 같은 env 의 mplib 또는 pinocchio 를 확인한다
    (scripts.ik_exec 이 같은 순서의 가용성으로 백엔드를 고른다)."""
    if sys.platform == "win32":
        return _check_wsl()
    try:
        import mplib  # noqa: F401  (Linux 네이티브)
        return _ok("ik_backend", "mplib import OK (native)")
    except ImportError:
        pass
    try:
        import pinocchio
        return _ok("ik_backend", f"pinocchio {pinocchio.__version__} import OK (native)")
    except ImportError:
        return _warn(
            "ik_backend", "mplib 도 pinocchio 도 import 되지 않음",
            "conda install -c conda-forge pinocchio — ee_verify·gr00t_eval 에만 필요",
        )


def _check_mac_vulkan_icd() -> CheckResult:
    """darwin 렌더 전제: sapien 은 Vulkan 로더만 번들 — 드라이버(MoltenVK ICD)는
    시스템(Homebrew) 것을 쓴다. 경로 지정은 scripts/__init__.py 가 한다."""
    from scripts import MAC_VK_ICD
    if Path(MAC_VK_ICD).is_file():
        return _ok("mac_vulkan_icd", f"MoltenVK ICD: {MAC_VK_ICD}")
    return _fail("mac_vulkan_icd", f"MoltenVK ICD 없음: {MAC_VK_ICD}",
                 "brew install molten-vk")


def run(fix: bool = False, check_wsl: bool = True) -> dict:
    """Verify the harness env; with fix=True, install the pip layer from requirements.txt.

    Returns {"passed": bool, "checks": [...]}. passed is True iff no check is at
    level "fail" (WSL/extras warns don't fail overall).
    """
    checks: list[CheckResult] = []
    fix_hint = "python scripts/check_maniskill_env.py --fix  (requirements.txt 설치)"

    # 1) core imports — the gate; without them sim/render can't run
    missing = _missing(CORE_IMPORTS)
    if missing and fix:
        _pip_install_requirements()
        missing = _missing(CORE_IMPORTS)  # re-check after install
    if missing:
        detail = f"missing: {', '.join(missing)}"
        fixmsg = fix_hint if not fix else \
            "설치 후에도 누락 — conda env/버전을 SETUP.md 로 점검 (env 자체가 없을 수 있음)"
        checks.append(_fail("core imports", detail, fixmsg))
        if check_wsl:
            checks.append(_check_ik_backend())
        return {"passed": False, "checks": checks}

    import mani_skill, sapien, torch  # noqa: E402  (now known-importable)
    checks.append(_ok("core imports",
                      f"mani_skill={mani_skill.__version__}, "
                      f"sapien={sapien.__version__}, torch={torch.__version__}"))
    checks.append(_ok("cuda_available_info",
                      f"torch.cuda.is_available()={torch.cuda.is_available()}"))

    # 2) optional extras (LeRobot 변환 / 리포트) — missing = warn, not fail
    missing_extra = _missing(EXTRA_IMPORTS)
    if missing_extra:
        checks.append(_warn("extras", f"missing: {', '.join(missing_extra)} "
                            f"(h5_to_lerobot·h5_report 에만 필요)", fix_hint))
    else:
        checks.append(_ok("extras", "pyarrow, imageio OK"))

    # 3) CPU sim
    try:
        import gymnasium as gym
        import mani_skill.envs  # noqa: F401
        env = gym.make("PickCube-v1", num_envs=1, obs_mode="state",
                       sim_backend="cpu", render_backend="cpu")
        env.reset(seed=0)
        env.close()
        checks.append(_ok("env_construct_reset", "PickCube-v1 cpu/cpu reset OK"))
    except Exception as e:
        checks.append(_fail("env_construct_reset", repr(e),
                            "패키지 손상 가능 — " + fix_hint))
        if check_wsl:
            checks.append(_check_ik_backend())
        return {"passed": False, "checks": checks}

    # 4) CPU render (darwin 은 먼저 MoltenVK ICD 전제부터)
    if sys.platform == "darwin":
        checks.append(_check_mac_vulkan_icd())
    try:
        import numpy as np
        env = gym.make("PickCube-v1", num_envs=1, obs_mode="rgb",
                       sim_backend="cpu", render_backend="cpu",
                       render_mode="rgb_array")
        env.reset(seed=0)
        frame = env.render()
        arr = frame[0].cpu().numpy() if hasattr(frame[0], "cpu") else np.asarray(frame[0])
        env.close()
        if arr.ndim == 3 and arr.shape[-1] == 3 and arr.dtype.kind in ("u", "i", "f"):
            checks.append(_ok("cpu_render",
                              f"frame shape={tuple(arr.shape)}, mean px={arr.mean():.1f}"))
        else:
            checks.append(_fail("cpu_render",
                                f"unexpected frame: shape={arr.shape} dtype={arr.dtype}"))
    except Exception as e:
        checks.append(_fail("cpu_render", repr(e), "패키지/드라이버 점검 — " + fix_hint))

    # 5) IK backend (optional; only ee_verify/gr00t_eval/task_to_h5 need it)
    if check_wsl:
        checks.append(_check_ik_backend())

    passed = not any(c["level"] == "fail" for c in checks)
    return {"passed": passed, "checks": checks}


def _print_report(title: str, result: dict) -> None:
    mark = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    print(f"\n=== {title} ===")
    for c in result["checks"]:
        line = f"  [{mark.get(c['level'], '?')}] {c['name']}"
        if c["detail"]:
            line += f"  -- {c['detail']}"
        print(line)
        if c["level"] != "pass" and c.get("fix"):
            print(f"         → {c['fix']}")
    overall = "PASS" if result["passed"] else "FAIL"
    print(f"\nOverall: {overall}\n")


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fix", action="store_true",
                   help="repair what's fixable: pip install -r requirements.txt")
    p.add_argument("--no-wsl", action="store_true",
                   help="skip the WSL mplib probe (Windows-only pipeline)")
    args = p.parse_args()
    result = run(fix=args.fix, check_wsl=not args.no_wsl)
    _print_report("ManiSkill Env Health Check", result)
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    _cli()
