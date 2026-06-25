"""torch 없는 가짜 GR00T 정책 서버 — 롤아웃 클라이언트 배관 로컬 테스트용.

진짜 모델(RunPod GPU)을 띄우기 전에 scripts/_wsl_gr00t_eval.py 의 전 경로
(obs 생성 → msgpack 와이어 → 액션 디코드 → rot6d→quat → mplib IK → sim step)를
로컬에서 검증한다. gr00t.policy.server_client.PolicyServer 의 get_action/ping 와이어
포맷만 흉내냄(msgpack + msgpack_numpy). 모델이 없으므로 "제자리(stay)" 액션을 돌려준다:
관측의 현재 abs-EEF 를 그대로 16-스텝 타깃으로 — IK 가 반드시 풀리는 reachable 타깃이라
배관 자체를 깨끗이 검증(성공률 의미 없음, ik_fails≈0 이면 통과).

  python scripts/_wsl_mock_server.py --port 5599
"""
import argparse
import sys

import msgpack
import msgpack_numpy as mnp
import numpy as np
import zmq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5599)
    ap.add_argument("--horizon", type=int, default=16)
    a = ap.parse_args()

    ctx = zmq.Context()
    s = ctx.socket(zmq.REP)
    s.bind(f"tcp://{a.host}:{a.port}")
    print(f"MOCK gr00t server up on {a.host}:{a.port} (horizon={a.horizon})", flush=True)

    n_act = 0
    while True:
        msg = msgpack.unpackb(s.recv(), object_hook=mnp.decode, raw=False)
        ep = msg.get("endpoint")
        if ep == "ping":
            s.send(msgpack.packb({"status": "ok"}, default=mnp.encode))
        elif ep == "kill":
            s.send(msgpack.packb({"status": "bye"}, default=mnp.encode))
            break
        elif ep == "get_action":
            obs = msg["data"]["observation"]
            cur = np.asarray(obs["state"]["eef"]).reshape(-1)[:9].astype(np.float32)  # (9,)
            act_eef = np.tile(cur, (1, a.horizon, 1)).astype(np.float32)   # (1,H,9) stay
            grip = np.zeros((1, a.horizon, 1), dtype=np.float32)           # (1,H,1)
            s.send(msgpack.packb([{"eef": act_eef, "gripper": grip}, {}], default=mnp.encode))
            n_act += 1
            if n_act % 20 == 0:
                print(f"  served {n_act} get_action", flush=True)
        else:
            s.send(msgpack.packb({"error": f"unknown endpoint {ep}"}, default=mnp.encode))

    s.close()
    ctx.term()
    print(f"MOCK server done ({n_act} get_action served)", flush=True)


if __name__ == "__main__":
    main()
