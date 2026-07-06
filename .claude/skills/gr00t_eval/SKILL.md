---
name: gr00t_eval
description: 학습된 GR00T 정책을 ManiSkill 시뮬레이션에 붙여 닫힌 루프로 직접 굴리고 태스크 성공률을 재는 배포 평가 스킬 (④-eval). scripts/gr00t_eval.py 래퍼 — 정책(GPU)은 원격(RunPod)에서 ZMQ 서버로 뜨고(gr00t_serve), 이 스킬이 WSL 롤아웃 클라이언트(_wsl_gr00t_eval.py: sim + mplib IK, torch 없음)를 구동해 서버에 붙는다. 매 스텝: sim obs(rgb+qpos+abs-EEF+언어) → 정책 get_action(절대 EEF) → rot6d→quat → mplib IK → env.step → success 판정. 입력은 SOURCE 이미지 데이터셋 h5(h5_add_images 출력 — episode_seed/label_metadata/tcp_pose 필요), LeRobot 디렉토리 아님. 평가 자체는 무과금(로컬 WSL)이나 떠 있는 정책 서버(gr00t_serve)는 과금 GPU 파드이므로 끝나면 runpod_down. 언어 명령은 환경의 instruction_template()에서 자동으로 읽는다(학습과 단일 출처). args = `<dataset-h5> --server-host <ip> [--count N] [--seed S] [--server-port 5555] [--action-steps 16] [--max-steps 0] [--task <id>]`.
---

# gr00t_eval — GR00T 정책 sim 롤아웃 평가 (④-eval)

`scripts/gr00t_eval.py` 래퍼. 학습된 GR00T 정책을 **시뮬레이션에 직접 붙여** 닫힌 루프로 굴리고 **태스크 성공률**을 잰다. 단순 함수가 아니라 진짜 sim-in-the-loop 배포 평가다:

```
ManiSkill env 생성 → 에피소드 seed로 reset
반복:
  sim obs (카메라 rgb + qpos + tcp_pose→abs-EEF + 언어)
    → ZMQ로 정책 서버 get_action  (원격 GPU의 GR00T가 추론, 절대 EEF 16스텝 호라이즌)
    → rot6d→quat → world 타깃 pose → mplib IK → 관절각
    → env.step(pd_joint_pos)        (--action-steps 만큼 실행 후 replan)
  success 또는 step budget까지
→ success_rate 집계
```

정책(GPU)은 원격(RunPod)에서 ZMQ 서버로 뜨고, 이 스킬이 Windows에서 WSL 롤아웃 클라이언트를 구동한다 (`ee_verify`·`task_to_h5` 와 동일 패턴). IK 실행부(env 구성 / world→base 프레임 변환 / mplib IK)는 `scripts/ik_exec.py` 를 **`ee_verify` 와 공유** — 그 핵심 경로는 ee_verify 게이트로 이미 검증된다.

## 전제조건

- **떠 있는 정책 서버** — `/gr00t_serve <hf_model>` 로 학습 모델을 5555/tcp 서버로 띄워야 함. `--server-host` 는 그 파드의 TCP 프록시 IP/호스트.
- **WSL 환경** (mplib + 소프트웨어 Vulkan) + 일회성 `pip install pyzmq msgpack msgpack-numpy` (WSL maniskill env).
- **SOURCE 이미지 데이터셋 h5** (`h5_add_images` 출력) — `obs/extra/tcp_pose`, `episode_seed`, `label_metadata` 필요. LeRobot 디렉토리는 안 됨(seed/label이 없음). 입력은 학습에 안 쓴 홀드아웃 세트(학습셋과 겹치지 않는 seed 구간; 아래 "순서" 참고).

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 토큰 = 데이터셋 HDF5 경로. **필수.**
   - `--server-host <ip>` **필수** — 정책 서버 호스트.
   - `--count N` (기본 10; `0` = 전체), `--seed S` (재현 가능한 랜덤 샘플)
   - 언어 명령은 환경의 `instruction_template()` 에서 **자동으로** 읽는다(학습 `h5_to_lerobot` 과 동일한 단일 출처 → 문구 안 어긋남) — 넘길 인자 없음.
   - `--server-port` (기본 5555), `--action-steps` (replan당 실행 액션 수, ≤ 호라이즌, 기본 16), `--max-steps` (에피소드당 step budget, `0`=기록 길이), `--task <id>` (기본: 사이드카 `env_id`), `--sim-backend cpu`
2. 프로젝트 루트에서 실행:
   ```
   <maniskill-python> scripts/gr00t_eval.py --traj-path "<PATH>" --server-host <ip> [--count N]
   ```
3. 결과 한 줄 보고: `episodes=N orig_success=.../N policy_success=.../N success_rate=... ik_fails=...`.

## 동작 / 주의사항

- **성공 기준 = `evaluate().success`** — 시뮬에서 그 과제를 실제로 해냈나(예: 타겟 큐브가 그릇 안 + 놓임 + 정지). 태스크 환경이 정의한 그대로, 별도 기준 없음.
- **`orig_success` = 공짜 자가 기준점** — 출력에 기록 에피소드의 성공률을 같이 찍는다. 성공 demo만 저장했으니 ~100%가 정상. 이 값이 이상하면(낮으면) 데이터/하네스를 의심하는 신호 — `policy_success` 와 분리해 "모델 탓 vs 도구 탓"을 가르는 데 쓴다.
- **프롬프트는 템플릿 구조** — 스텝마다 실시간 입력이 아니라, 에피소드당 1개의 템플릿을 라벨로 채워 모델에 언어 입력으로 준다. 학습 분포와 같은 문장이어야 정직한 측정.
- **GR00T 규약에 묶임(모델엔 안 묶임)** — 어떤 GR00T 파인튜닝 체크포인트든 `--server-host` 로 갈아끼울 수 있으나, 와이어포맷(msgpack)·모달리티 키(`base_camera` 비디오 / `qpos+eef` 상태 / `eef+gripper` 액션 / 언어키 `annotation.human.task_description`)는 GR00T + 우리 임베디먼트 규약(`new_embodiment_config.py`)에 고정. 카메라는 이름(`base_camera`)으로 선택 — 없으면 명확히 실패.
- **닫힌 루프 / open-loop 드리프트 허용** — ee_verify(기록 waypoint 추종)와 달리 정책이 매 replan마다 현재 obs로 보정한다. 그래서 정책 성공률은 모델의 실제 추종력을 잰다.
- **순서**: `h5_to_lerobot`(포장) → `gr00t_train`(학습) → `gr00t_serve`(서빙) → **`gr00t_eval`**(평가). 입력은 학습셋이 아니라 홀드아웃 h5 — 겹치지 않는 seed 구간에서 `task_to_h5 --start-seed <N>` → `h5_add_images` 로 따로 만든다(lerobot/hf 변환 불필요). MANIFEST 는 이 값을 `eval_method: v2` 로 기록.
- **과금**: 평가 실행 자체는 로컬 WSL(무과금)이나, 전제인 정책 서버는 과금 GPU 파드다. 평가 끝나면 `/runpod_ls` 확인 후 `/runpod_down`.
- 시뮬만 돌고 파일은 안 만든다 (순수 평가).

## 모니터링·폴링

평가 실행 자체는 무과금(로컬 WSL)이나 **떠 있는 정책 서버(5555)에 의존**한다. RunPod 공통
운영 규칙은 **`cloud/RUNPOD_OPS.md`**, serve 부팅 폴링은 `gr00t_serve` 참조. eval 고유:

- `--server-host`/`--server-port` 는 serve 파드의 `runpod_client.pod().portMappings` 에서 얻는다
  (`runpod_ls` 는 포트 안 보여줌).
- serve 준비 전엔 `client.ping()` 이 fail-fast — 5555 가 열렸는지(TCP connect/ping) 확인한 뒤
  롤아웃을 시작한다.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/gr00t_eval data/datasets/ColoredCubeInBowl-v1/motionplanning.rgb.pd_joint_pos.physx_cpu.h5 --server-host 1.2.3.4` | 랜덤 10개 닫힌 루프 롤아웃 → 성공률 (명령은 환경 템플릿) |
| `/gr00t_eval <hdf5> --server-host <ip> --count 0 --seed 42` | 전체 에피소드 평가(재현 가능) |

흐름: `/gr00t_serve <model>`(서빙) → **`/gr00t_eval <소스 h5> --server-host <ip>`**(평가) → `/runpod_down`(종료).
