"""Health check for the ManiSkill harness install (is the environment working?).

Verifies the pieces every other skill depends on: core imports, CPU simulation,
and the CPU render path (the one this harness uses on Windows). Run it once after
setup, or whenever something breaks, to tell "my environment is broken" apart from
"my data/code is wrong".

(Dataset structure validation is intentionally NOT here — a produced HDF5 is
checked at generation time, and any deeper, purpose-specific validation belongs to
a later training-prep step, not to this environment health check.)

Returns a dict ``{"passed": bool, "checks": [...]}``.

Two interfaces:
  - Python:  from scripts.check_maniskill_env import run; run()
  - CLI:     python scripts/check_maniskill_env.py
"""
from __future__ import annotations

import sys


CheckResult = dict  # {"name": str, "passed": bool, "detail": str}


def _ok(name: str, detail: str = "") -> CheckResult:
    return {"name": name, "passed": True, "detail": detail}


def _fail(name: str, detail: str) -> CheckResult:
    return {"name": name, "passed": False, "detail": detail}


def _print_report(title: str, result: dict) -> None:
    print(f"\n=== {title} ===")
    for c in result["checks"]:
        mark = "PASS" if c["passed"] else "FAIL"
        line = f"  [{mark}] {c['name']}"
        if c["detail"]:
            line += f"  -- {c['detail']}"
        print(line)
    overall = "PASS" if result["passed"] else "FAIL"
    print(f"\nOverall: {overall}\n")


def run() -> dict:
    """Run a quick functional check of the ManiSkill install + CPU render path."""
    checks: list[CheckResult] = []

    try:
        import mani_skill, sapien, gymnasium, h5py, torch  # noqa: F401
        from PIL import Image  # noqa: F401
        checks.append(_ok("imports",
                          f"mani_skill={mani_skill.__version__}, "
                          f"sapien={sapien.__version__}, torch={torch.__version__}"))
    except Exception as e:
        checks.append(_fail("imports", repr(e)))
        return {"passed": False, "checks": checks}

    import torch
    checks.append(_ok("cuda_available_info",
                      f"torch.cuda.is_available()={torch.cuda.is_available()}"))

    try:
        import gymnasium as gym
        import mani_skill.envs  # noqa: F401
        env = gym.make("PickCube-v1", num_envs=1, obs_mode="state",
                       sim_backend="cpu", render_backend="cpu")
        env.reset(seed=0)
        env.close()
        checks.append(_ok("env_construct_reset", "PickCube-v1 cpu/cpu reset OK"))
    except Exception as e:
        checks.append(_fail("env_construct_reset", repr(e)))
        return {"passed": all(c["passed"] for c in checks), "checks": checks}

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
        checks.append(_fail("cpu_render", repr(e)))

    passed = all(c["passed"] for c in checks)
    return {"passed": passed, "checks": checks}


def _cli() -> None:
    result = run()
    _print_report("ManiSkill Env Health Check", result)
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    _cli()
