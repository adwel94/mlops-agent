---
name: gr00t_play
description: 파인튜닝한 GR00T 모델을 SAPIEN 뷰어 창에서 라이브로 조종하는 인터랙티브 플레이그라운드 (macOS/Linux 네이티브). scripts/gr00t_play.py 래퍼 — MANIFEST.yaml 좌표(<task>/<model>, 예 threecubes/v2-s20000)만 받아 환경(env_id)·카메라/robot_uids(HF modality.json)·예시 명령(HF tasks.jsonl)을 역추적해 구축하고, RunPod 정책 서버(gr00t_serve)에 ZMQ 로 붙는다. MANIFEST 에 등록된(이 하네스로 학습한) 모델만 대상. 터미널 REPL 로 자유 자연어 명령·reset·stop 을 주면 로봇이 뷰어 창에서 실행한다. REPL 은 사용자 터미널 stdin 이 필요하므로 AI 가 직접 띄우지 않고, 서버 준비까지 마친 뒤 실행 명령 한 줄을 사용자에게 건넨다. 정책 서버는 과금 GPU 파드 — 없으면 승인받아 gr00t_serve 로 띄우고, 플레이가 끝나면 /runpod_down 안내. args = `<task>/<model> [--server-host IP] [--seed S] [--action-steps 16]`.
---

# gr00t_play — 학습 모델 인터랙티브 플레이 (뷰어 + 자연어 REPL)

`scripts/gr00t_play.py` 래퍼. 배치 채점(`gr00t_eval`)이 아니라 **사람이 직접 명령을
던지며 보는** 용도다:

```
MANIFEST 좌표 (threecubes/v2-s20000)
  → env_id(MANIFEST) + 카메라·robot_uids(HF modality.json) + 예시 명령(HF tasks.jsonl)
  → SAPIEN 뷰어 창(human 렌더) + 터미널 REPL
  → <자유 명령> 입력 → ZMQ get_action → IK → env.step (스텝마다 렌더)
```

## 전제조건

- **MANIFEST 등록 모델만** — `MANIFEST.yaml` 의 `<task>/<model>` 좌표. 태스크 키에
  `env_id` 필드가 있어야 한다.
- **떠 있는 정책 서버** — `/gr00t_serve <repo> --revision <tag>` (과금). 모델 repo/tag 는
  MANIFEST 의 그 모델 항목에서 읽는다.
- macOS/Linux 네이티브 환경 (`check_maniskill_env` PASS — pinocchio·렌더).

## 호출됐을 때

1. `args` 파싱: 첫 토큰 = `<task>/<model>` 좌표 (**필수**). `--server-host` 가 있으면 3으로.
2. **정책 서버 확보** (`--server-host` 없을 때):
   - `runpod_ls` 로 serve 파드가 이미 떠 있는지 확인.
   - 없으면 MANIFEST 에서 그 모델의 `repo`/`tag` 를 읽어 **사용자 승인 후**
     `/gr00t_serve <repo> --revision <tag>` 로 띄운다 (과금 시작을 명시).
   - 파드의 5555/tcp 공개 IP:포트는 `runpod_client.pod().portMappings` 로 얻는다.
   - 파드를 새로 띄우게 되면(스크립트 직접 실행 포함) 생성 전 `cloud/RUNPOD_OPS.md` 를
     통독한다 — 폴링·준비 판단(준비 = 5555 바인딩, `RUNNING` 은 컨테이너만 뜬 것)·진행
     리포팅 규칙이 거기 있다.
3. **실행 명령을 사용자에게 건넨다** — REPL 이 사용자 키보드를 받아야 하므로 AI 가
   백그라운드로 띄우지 않는다. 사용자 터미널에서 실행하도록 한 줄을 출력:
   ```
   conda run -n maniskill --no-capture-output python scripts/gr00t_play.py \
     --model <task>/<model> --server-host <IP> --server-port <PORT>
   ```
   (배선만 볼 때는 `--mock` 으로 서버 없이 실행 가능하다고 안내.)
4. **입력할 예시 명령을 함께 건넨다** — 스크립트도 REPL 시작 시 출력하지만, 사용자는
   실행 *전에* 무엇을 시킬지 알아야 한다. 학습된 문장이 곧 유효 입력이므로 그대로 보여준다
   (태스크 이름을 모른 채 데이터에서 읽는다 — 새 태스크에도 코드 불변):
   ```
   python -c "import sys; sys.path.insert(0,'.'); \
     from scripts.gr00t_play import resolve_model, fetch_dataset_meta as m; \
     s=resolve_model('<task>/<model>'); \
     print(*m(s['dataset_repo'], s['dataset_tag'])['instructions'], sep='\n')"
   ```
   문장은 환경의 `instruction_template()` 이 단일 출처다(학습·평가·플레이가 같은 문구).
   틀 밖의 명령도 REPL 이 받지만 학습 분포 밖이라 거동이 무너지는 게 정상이라고 알린다.
5. 플레이 종료 후: 파드가 떠 있으면 과금 중이므로 `/runpod_down` 을 안내한다.

## REPL 명령 (스크립트가 시작 시 예시 명령과 함께 출력)

- `<자유 자연어>` — 실행 시작 (실행 중이면 다음 replan 에 교체)
- `reset [seed]` — 씬 재배치 · `stop` — 팔 정지 · `quit` — 종료 (뷰어 창 닫아도 종료)
