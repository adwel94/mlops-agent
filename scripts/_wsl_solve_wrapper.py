"""WSL-side wrapper for action generation via ManiSkill motion planning.

This file is NOT meant to run on Windows. `scripts/solve.py` invokes it through
`wsl.exe` using the WSL conda env's Python (it sits on the shared C: drive and is
reached via /mnt/c/...). It applies the two workarounds needed to run sapien
headless on WSL's software (llvmpipe) Vulkan, then delegates to ManiSkill's
panda motion-planning `run` module, forwarding all CLI args verbatim.

Workarounds (mirror the Windows harness's gym.make monkey-patch philosophy):
  1. render_backend='cpu' injection — WSL has no GPU Vulkan, so don't ask for one.
  2. RenderSystem auto-fallback — ManiSkill passes an explicit 'cpu' sapien.Device
     that sapien's renderer rejects ("single-GPU rendering only"); retry with no
     argument so sapien auto-selects the supported llvmpipe device.

The caller is responsible for exporting VK_ICD_FILENAMES to the lavapipe ICD so
the software renderer is the one picked.
"""
import sys

import sapien.render as _R

_orig_render_system = _R.RenderSystem


def _safe_render_system(*args, **kwargs):
    try:
        return _orig_render_system(*args, **kwargs)
    except RuntimeError:
        # explicit device rejected -> let sapien auto-select (llvmpipe / software)
        return _orig_render_system()


_R.RenderSystem = _safe_render_system

import gymnasium as gym  # noqa: E402

_orig_make = gym.make


def _patched_make(env_id, *args, **kwargs):
    kwargs.setdefault("render_backend", "cpu")
    return _orig_make(env_id, *args, **kwargs)


gym.make = _patched_make

from mani_skill.examples.motionplanning.panda import run  # noqa: E402

if __name__ == "__main__":
    run.main(run.parse_args(sys.argv[1:]))
