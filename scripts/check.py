"""Health checks for the ManiSkill harness install and for generated datasets.

Two functions, both returning a dict ``{"passed": bool, "checks": [...]}``:

  - ``install()``         — verify env imports, CPU sim + render work
  - ``dataset(path)``     — verify an HDF5 file has the expected VLA structure

CLI:
  python scripts/check.py --install
  python scripts/check.py --dataset <PATH_TO_HDF5>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


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


def install() -> dict:
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

    demos_root = Path.home() / ".maniskill" / "demos"
    tasks = ([p.name for p in demos_root.iterdir() if p.is_dir()]
             if demos_root.exists() else [])
    if tasks:
        checks.append(_ok("demos_present", f"tasks downloaded: {sorted(tasks)}"))
    else:
        checks.append(_ok("demos_present_info",
                          "no demos downloaded yet (run scripts/setup.py)"))

    passed = all(c["passed"] for c in checks)
    return {"passed": passed, "checks": checks}


def dataset(path: str | Path, verbose: bool = False) -> dict:
    """Inspect an HDF5 dataset file for VLA-style integrity."""
    import h5py
    import numpy as np

    checks: list[CheckResult] = []
    p = Path(path)

    if not p.exists():
        return {"passed": False, "checks": [_fail("file_exists", str(p))]}
    checks.append(_ok("file_exists",
                      f"{p} ({p.stat().st_size / 1024 / 1024:.2f} MB)"))

    try:
        f = h5py.File(p, "r")
    except Exception as e:
        checks.append(_fail("hdf5_readable", repr(e)))
        return {"passed": False, "checks": checks}

    with f:
        trajs = sorted(f.keys())
        if not trajs:
            checks.append(_fail("has_episodes", "no traj_* keys found"))
            return {"passed": False, "checks": checks}
        checks.append(_ok("has_episodes", f"{len(trajs)} episodes"))

        lengths, rgb_shapes, rgb_dtypes, succ = [], set(), set(), 0
        missing_fields: dict[str, int] = {}
        cam_name = None

        for k in trajs:
            tr = f[k]
            for need in ("actions", "obs", "success"):
                if need not in tr:
                    missing_fields[need] = missing_fields.get(need, 0) + 1
            if "actions" in tr:
                lengths.append(tr["actions"].shape[0])
            if "success" in tr and bool(tr["success"][-1]):
                succ += 1
            sd = tr.get("obs", {}).get("sensor_data") if "obs" in tr else None
            if sd is not None and len(sd.keys()) > 0:
                cam_name = cam_name or list(sd.keys())[0]
                cam = sd[cam_name]
                if "rgb" in cam:
                    rgb_shapes.add(tuple(cam["rgb"].shape[1:]))
                    rgb_dtypes.add(str(cam["rgb"].dtype))

        if missing_fields:
            checks.append(_fail("required_fields_present", str(missing_fields)))
        else:
            checks.append(_ok("required_fields_present",
                              "actions/obs/success all present"))

        if lengths:
            checks.append(_ok("episode_lengths",
                              f"min/mean/max steps = "
                              f"{min(lengths)}/{np.mean(lengths):.1f}/{max(lengths)}"))

        checks.append(_ok("success_rate",
                          f"{succ}/{len(trajs)} = "
                          f"{(succ / len(trajs) * 100):.1f}%"))

        if rgb_shapes:
            if len(rgb_shapes) == 1:
                checks.append(_ok("rgb_shape_consistent",
                                  f"camera '{cam_name}' frames {next(iter(rgb_shapes))} "
                                  f"dtype {next(iter(rgb_dtypes))}"))
            else:
                checks.append(_fail("rgb_shape_consistent",
                                    f"inconsistent shapes across episodes: {rgb_shapes}"))
        else:
            checks.append(_ok("rgb_shape_info", "no RGB camera in this dataset"))

    passed = all(c["passed"] for c in checks)
    return {"passed": passed, "checks": checks}


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--install", action="store_true",
                   help="Verify the ManiSkill install + CPU sim/render")
    g.add_argument("--dataset", metavar="PATH",
                   help="Verify an HDF5 dataset at PATH")
    args = p.parse_args()

    if args.install:
        result = install()
        _print_report("Install Health Check", result)
    else:
        result = dataset(args.dataset)
        _print_report(f"Dataset Check: {args.dataset}", result)

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    _cli()
