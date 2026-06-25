"""GR00T 정책 서버(ZMQ)가 응답할 때까지 ping (WSL, torch 없음).

파드가 부팅 때 bootstrap(uv sync, flash-attn) → serve 를 끝내야 5555 가 응답한다.
이 스크립트는 host:port 로 REQ ping 을 반복해, 서버가 뜨면 0, 시간 초과면 1 로 종료.
gr00t_eval 의 PolicyClient 와 동일 와이어 포맷(msgpack + msgpack_numpy).

  python scripts/_wsl_ping_server.py <host> <port> [max_tries] [sleep_s]
"""
import sys
import time

import msgpack
import msgpack_numpy as mnp
import zmq

host = sys.argv[1]
port = int(sys.argv[2])
max_tries = int(sys.argv[3]) if len(sys.argv) > 3 else 120
sleep_s = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0

ctx = zmq.Context()
req = msgpack.packb({"endpoint": "ping", "data": {}}, default=mnp.encode)

for i in range(max_tries):
    s = ctx.socket(zmq.REQ)
    s.setsockopt(zmq.RCVTIMEO, 5000)
    s.setsockopt(zmq.SNDTIMEO, 5000)
    s.setsockopt(zmq.LINGER, 0)
    s.connect(f"tcp://{host}:{port}")
    try:
        s.send(req)
        rep = msgpack.unpackb(s.recv(), object_hook=mnp.decode, raw=False)
        print(f"SERVER_UP after {i} tries ({i * sleep_s:.0f}s): {rep}", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"[{i}] not ready: {type(e).__name__}", flush=True)
    finally:
        s.close()
    time.sleep(sleep_s)

print(f"TIMEOUT: server not up after {max_tries} tries", flush=True)
sys.exit(1)
