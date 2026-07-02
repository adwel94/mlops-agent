"""Interactive GR00T playground — 파인튜닝 모델을 SAPIEN 뷰어 창에서 라이브로 조종.

MANIFEST.yaml 좌표(`<task>/<model>`, 예: threecubes/v2-s20000)만 받아 그 모델의 실행
환경을 통째로 역추적해 구축한다: env_id(MANIFEST) → 시뮬 환경, HF 데이터셋
meta/modality.json → 카메라 세트·robot_uids, meta/tasks.jsonl → 학습된 예시 명령.
MANIFEST 에 등록된(=이 하네스로 학습한) 모델만 대상이다 — 외부 모델은 다루지 않는다.

정책(GPU)은 gr00t_eval 과 동일하게 RunPod 의 ZMQ 서버(gr00t_serve)가 맡고, 이 프로세스는
sim + IK + 뷰어 + 터미널 REPL 만 돈다. 매 replan 마다: 현재 obs(rgb+qpos+abs-EEF+명령)
→ get_action → rot6d→quat → IK(solve_to_arm) → env.step, 스텝마다 뷰어 렌더.

터미널 명령: <자유 자연어> = 실행 시작/교체 · reset [seed] = 씬 재배치 ·
stop = 팔 정지 · quit = 종료 (뷰어 창을 닫아도 종료).

  - Python:  from scripts.gr00t_play import run; run("threecubes/v2-s20000", server_host="1.2.3.4")
  - CLI:     python scripts/gr00t_play.py --model threecubes/v2-s20000 --server-host 1.2.3.4
  - 배선 테스트(무과금, 서버 불필요):  --mock  (현재 EEF 를 유지하는 모의 정책)
"""
from __future__ import annotations

import argparse
import json
import queue
import random
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import numpy as np

from scripts import manifest
from scripts.env_config import load_env
from scripts.ee_convert import rot6d_to_quat
from scripts.h5_to_lerobot import select_cameras
from scripts.ik_exec import np1, make_env_and_solver, solve_to_arm


# ---- 모델 좌표 해석 (MANIFEST → env / HF 데이터셋 meta) -----------------------

def resolve_model(coord: str) -> dict:
    """`<task>/<model>` (예: threecubes/v2-s20000) → 실행 스펙.

    반환: {task_key, model_key, env_id, model_repo, model_tag,
           dataset_repo, dataset_tag}
    """
    if "/" not in coord:
        raise ValueError(f"모델 좌표는 <task>/<model> 형식: {coord!r} "
                         f"(예: threecubes/v2-s20000)")
    task_key, model_key = coord.split("/", 1)
    data = manifest.load()
    if task_key not in data:
        raise KeyError(f"MANIFEST 에 태스크 {task_key!r} 없음. 있는 것: {sorted(data)}")
    entry = data[task_key]
    env_id = entry.get("env_id")
    if not env_id:
        raise KeyError(f"MANIFEST {task_key} 에 env_id 없음 — 태스크 키 아래 "
                       f"`env_id: <EnvId-v1>` 한 줄을 추가해야 플레이 가능")
    models = entry.get("models") or {}
    if model_key not in models:
        raise KeyError(f"MANIFEST {task_key} 에 모델 {model_key!r} 없음. "
                       f"있는 것: {sorted(models)}")
    model = models[model_key]
    ds_key = model["dataset"]
    ds = (entry.get("datasets") or {})[ds_key]
    return {
        "task_key": task_key, "model_key": model_key, "env_id": env_id,
        "model_repo": model["repo"], "model_tag": model.get("tag"),
        "dataset_repo": ds["repo"], "dataset_tag": ds.get("tag"),
    }


def fetch_dataset_meta(dataset_repo: str, dataset_tag: str | None) -> dict:
    """HF 데이터셋 meta 에서 카메라 세트와 학습 명령 문장들을 읽는다.

    반환: {cams: [name...], robot_uids, instructions: [str...]}
    카메라는 modality.json 의 video 키(=env 센서 이름 계약)에서 발견하고,
    robot_uids 는 hand_camera 유무로 정해진다 (h5_add_images 가 wrist 캠 데이터셋을
    panda_wristcam 으로 만들었다는 그 계약의 역방향).
    """
    from huggingface_hub import hf_hub_download
    kw = dict(repo_id=dataset_repo, repo_type="dataset", revision=dataset_tag)
    modality = json.loads(Path(hf_hub_download(
        filename="meta/modality.json", **kw)).read_text(encoding="utf-8"))
    cams = select_cameras(list(modality["video"]))
    tasks_file = Path(hf_hub_download(filename="meta/tasks.jsonl", **kw))
    instructions = [json.loads(line)["task"]
                    for line in tasks_file.read_text(encoding="utf-8").splitlines()
                    if line.strip()]
    return {
        "cams": cams,
        "robot_uids": "panda_wristcam" if "hand_camera" in cams else "panda",
        "instructions": instructions,
    }


# ---- 정책 클라이언트 ----------------------------------------------------------

class MockPolicy:
    """서버 없는 배선 테스트용 — 현재 EEF 를 유지하는 액션(그리퍼 열림)을 돌려준다."""

    def __init__(self, horizon: int = 16):
        self.horizon = horizon

    def ping(self):
        return {"status": "mock"}

    def get_action(self, observation, options=None):
        eef = np.asarray(observation["state"]["eef"][0, 0], dtype=float)   # (9,)
        return {
            "eef": np.tile(eef, (1, self.horizon, 1)),          # (1,H,9)
            "gripper": np.ones((1, self.horizon, 1)),           # (1,H,1) = open
        }

    def close(self):
        pass


def _make_policy(mock: bool, server_host: str | None, server_port: int):
    if mock:
        return MockPolicy()
    if not server_host:
        raise ValueError("--server-host 필요 (gr00t_serve 로 띄운 정책 서버) — "
                         "서버 없이 배선만 볼 땐 --mock")
    from scripts._wsl_gr00t_eval import PolicyClient
    return PolicyClient(server_host, server_port)


# ---- REPL ---------------------------------------------------------------------

HELP = """명령:
  <자유 자연어>   그 명령으로 실행 시작 (실행 중이면 다음 replan 부터 교체)
  reset [seed]    씬 재배치 (seed 생략 = 랜덤)
  stop            팔 정지 (명령 대기로)
  quit            종료 (뷰어 창을 닫아도 종료)"""


def _stdin_reader(q: "queue.Queue[str]") -> None:
    while True:
        try:
            line = input()
        except EOFError:            # 파이프 입력 끝 = quit
            q.put("quit")
            return
        q.put(line.strip())


def run(
    model: str,
    server_host: str | None = None,
    server_port: int = 5555,
    action_steps: int = 16,
    sim_backend: str = "cpu",
    seed: int | None = None,
    mock: bool = False,
) -> None:
    """MANIFEST 좌표의 모델로 인터랙티브 플레이 세션을 연다 (닫힐 때까지 블로킹)."""
    load_env()                       # HF_TOKEN (private repo 대비)
    spec = resolve_model(model)
    meta = fetch_dataset_meta(spec["dataset_repo"], spec["dataset_tag"])
    print(f"[gr00t_play] model {spec['model_repo']}"
          f"{':' + spec['model_tag'] if spec['model_tag'] else ''}"
          f"  →  env {spec['env_id']}  cams {meta['cams']}  ({meta['robot_uids']})")

    policy = _make_policy(mock, server_host, server_port)
    policy.ping()                    # 서버 연결 fail-fast

    import scripts.custom_envs  # noqa: F401  (등록; ik_exec 도 하지만 명시)
    from scripts._wsl_gr00t_eval import _build_obs
    env, base, solver, base_p, base_q = make_env_and_solver(
        spec["env_id"], sim_backend=sim_backend, obs_mode="rgb",
        robot_uids=meta["robot_uids"], render_mode="human",
    )
    obs, _ = env.reset(seed=seed if seed is not None else random.randrange(2**31))
    viewer = env.unwrapped.render_human()

    print(f"\n[gr00t_play] 이 모델이 학습한 명령 예시 ({len(meta['instructions'])}개):")
    for t in meta["instructions"][:10]:
        print(f"  - {t}")
    print(f"\n{HELP}\n", flush=True)

    cmd_q: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=_stdin_reader, args=(cmd_q,), daemon=True).start()

    instr: str | None = None         # None = 대기(팔 정지, 뷰어만 갱신)
    last_q = np1(base.agent.robot.get_qpos())
    steps = ik_fails = 0

    def _viewer_alive() -> bool:
        return not getattr(viewer, "closed", False)

    while _viewer_alive():
        # 1) 명령 처리 (대기 중엔 블로킹 폴링, 실행 중엔 논블로킹)
        try:
            line = cmd_q.get(timeout=0.02 if instr is None else 0.0)
        except queue.Empty:
            line = None
        if line is not None:
            low = line.lower()
            if low in ("quit", "exit"):
                break
            elif low == "help":
                print(HELP, flush=True)
            elif low == "stop":
                instr = None
                print("[gr00t_play] 정지 — 명령 대기", flush=True)
            elif low.startswith("reset"):
                parts = line.split()
                s = int(parts[1]) if len(parts) > 1 else random.randrange(2**31)
                obs, _ = env.reset(seed=s)
                last_q = np1(base.agent.robot.get_qpos())
                instr, steps, ik_fails = None, 0, 0
                print(f"[gr00t_play] reset (seed={s}) — 명령 대기", flush=True)
            elif line:
                instr, steps, ik_fails = line, 0, 0
                print(f"[gr00t_play] ▶ \"{instr}\"", flush=True)

        # 2) 대기 상태: 뷰어만 갱신 (마우스로 카메라 조작 가능)
        if instr is None:
            env.unwrapped.render_human()
            continue

        # 3) 실행: replan 한 번 → action_steps 실행 (스텝마다 뷰어 렌더)
        _t0 = time.time()
        action = policy.get_action(_build_obs(obs, meta["cams"], instr))
        infer_ms = int(1000 * (time.time() - _t0))
        eef = np.asarray(action["eef"])[0]           # (H,9) absolute xyz+rot6d
        grip = np.asarray(action["gripper"])[0]      # (H,1)
        for h in range(min(action_steps, eef.shape[0])):
            if not _viewer_alive() or instr is None:
                break
            tp = eef[h, :3].astype(float)
            tq = rot6d_to_quat(eef[h, 3:9].astype(float))
            arm, failed = solve_to_arm(solver, tp, tq, base_p, base_q, last_q)
            ik_fails += int(failed)
            obs, _r, _term, _trunc, info = env.step(np.hstack([arm, float(grip[h, 0])]))
            last_q = np1(base.agent.robot.get_qpos())
            env.unwrapped.render_human()
            steps += 1
            if bool(np.asarray(info["success"]).reshape(-1)[0]):
                print(f"[gr00t_play] ✅ success! (steps={steps}, ik_fails={ik_fails}) "
                      f"— 명령 대기 (reset 으로 재배치)", flush=True)
                instr = None
                break
        if instr is not None:
            print(f"[gr00t_play]   … steps={steps} ik_fails={ik_fails} "
                  f"infer={infer_ms}ms", flush=True)

    policy.close()
    env.close()
    print("[gr00t_play] 종료", flush=True)


def _cli() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", required=True,
                   help="MANIFEST 좌표 <task>/<model>, 예: threecubes/v2-s20000")
    p.add_argument("--server-host", default=None,
                   help="gr00t_serve 정책 서버 host (--mock 이면 불필요)")
    p.add_argument("--server-port", type=int, default=5555)
    p.add_argument("--action-steps", type=int, default=16,
                   help="replan 당 실행 스텝 수 (<= GR00T 호라이즌)")
    p.add_argument("--sim-backend", default="cpu")
    p.add_argument("--seed", type=int, default=None, help="첫 씬 seed (기본 랜덤)")
    p.add_argument("--mock", action="store_true",
                   help="정책 서버 없이 배선 테스트 (현재 EEF 유지 모의 정책)")
    args = p.parse_args()
    run(args.model, server_host=args.server_host, server_port=args.server_port,
        action_steps=args.action_steps, sim_backend=args.sim_backend,
        seed=args.seed, mock=args.mock)


if __name__ == "__main__":
    _cli()
