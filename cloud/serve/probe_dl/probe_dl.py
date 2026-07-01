"""Dataset-download probe — runs inside a minimal RunPod pod.

The training pod's `prepare_dataset` (huggingface_hub.snapshot_download) hangs
deterministically ~halfway through our ~2000-file LeRobot dataset, but ONLY on
RunPod (it downloads fine locally). This probe reproduces that in the real pod
network and A/B-tests candidate fixes in one shot, reporting to the Discord
STDOUT webhook so the operator can read the verdict via read_logs.py.

Each variant runs in its own SUBPROCESS with a wall-clock timeout, so a hung
download is cleanly killed (you can't force-kill a hung thread, but you can a
process) and we record how far it got before stalling.

env: HF_DATASET (required), HF_TOKEN (optional), STDOUT_WEBHOOK_URL (optional).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

DATASET = os.environ["HF_DATASET"]
WEBHOOK = os.environ.get("STDOUT_WEBHOOK_URL")
BASE = "/tmp/dlprobe"

# child: download once, print where it got to. Progress (tqdm) -> stderr.
DL_CODE = r"""
import os, time
from huggingface_hub import snapshot_download
t = time.time()
snapshot_download(
    os.environ["HF_DATASET"], repo_type="dataset",
    local_dir=os.environ["DL_DIR"], token=os.environ.get("HF_TOKEN") or None,
    max_workers=int(os.environ.get("MW", "8")),
)
print("OK done in %.1fs" % (time.time() - t), flush=True)
"""


def _s(x):
    """Coerce subprocess output to str — TimeoutExpired.stdout is bytes even
    with text=True (the decode in communicate() never completes on timeout)."""
    if x is None:
        return ""
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else x


def post(msg):
    """Print + best-effort POST to the Discord STDOUT webhook."""
    print(msg, flush=True)
    if not WEBHOOK:
        return
    try:
        data = json.dumps({"content": msg[:1900]}).encode()
        req = urllib.request.Request(
            WEBHOOK, data=data, headers={
                "Content-Type": "application/json",
                # Discord/Cloudflare 403s the default python-urllib UA.
                "User-Agent": "Mozilla/5.0 (dl-probe)",
            })
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:  # noqa: BLE001 — reporting must never crash the probe
        print(f"[probe] webhook error: {e}", flush=True)


def run_variant(name, extra_env, timeout):
    """Download in a subprocess; return a one-line verdict (DONE/HUNG/FAIL)."""
    env = dict(os.environ)
    d = f"{BASE}/{name}"
    shutil.rmtree(d, ignore_errors=True)
    env["DL_DIR"] = d
    env["HF_HOME"] = f"{BASE}/hf_{name}"   # isolate cache so each starts cold
    env.update(extra_env)
    t = time.time()
    try:
        r = subprocess.run(
            [sys.executable, "-u", "-c", DL_CODE], env=env,
            capture_output=True, text=True, timeout=timeout)
        dt = time.time() - t
        out = _s(r.stdout) + _s(r.stderr)
        if "OK done" in out:
            return f"[{name}] DONE in {dt:.0f}s"
        tail = out.strip().splitlines()[-1][-200:] if out.strip() else "(no output)"
        return f"[{name}] FAIL rc={r.returncode} {dt:.0f}s :: {tail}"
    except subprocess.TimeoutExpired as e:
        dt = time.time() - t
        out = _s(e.stdout) + _s(e.stderr)
        hits = re.findall(r"files:\s*(\d+)it", out)
        where = hits[-1] if hits else "?"
        return f"[{name}] HUNG/TIMEOUT after {dt:.0f}s :: stalled ~{where} files"


def main():
    post(f"🔬 dl-probe START — dataset={DATASET} token={'yes' if os.environ.get('HF_TOKEN') else 'no'}")
    variants = [
        ("baseline",            {"MW": "8"},                                              100),
        ("hf_transfer",         {"MW": "8", "HF_HUB_ENABLE_HF_TRANSFER": "1"},            150),
        ("lowworkers_timeout",  {"MW": "4", "HF_HUB_DOWNLOAD_TIMEOUT": "15"},             200),
    ]
    results = []
    for name, extra, to in variants:
        try:
            v = run_variant(name, extra, to)
        except Exception as e:  # noqa: BLE001 — one variant must not abort the rest
            v = f"[{name}] PROBE-ERROR {type(e).__name__}: {e}"
        results.append(v)
        post(v)
    post("🔬 dl-probe DONE\n" + "\n".join(results))


if __name__ == "__main__":
    main()
