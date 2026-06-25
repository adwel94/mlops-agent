# h5_to_lerobot — 데이터셋을 GR00T LeRobot v2.1(절대 EEF)로 변환

`scripts/h5_to_lerobot.py` 래퍼. 이미지 데이터셋(`h5_add_images` 출력)을 GR00T-flavored LeRobot v2.1 포맷으로 포장한다. 기록된 tcp_pose를 **절대 엔드이펙터(xyz + rot6d, 9d)** 로 변환(`scripts/ee_convert.py`)해 gripper와 합친 10d 액션으로 쓰고, 프레임은 mp4로, 수치는 parquet로, 스키마·정규화·언어·`modality.json`은 meta로 떨군다. GR00T EEF 분기의 **생산** 단계.

순수 오프라인 — sim·WSL 없음. `pyarrow + imageio`만 사용(이미 설치됨), `lerobot` 라이브러리 의존 없음 → 작동 중인 conda env를 안 건드린다.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 토큰 = 데이터셋 HDF5 경로 (`h5_add_images` 출력 — rgb + `obs/extra/tcp_pose` 필요). **필수.**
   - 옵션 `--instruction "<template>"` — `label_metadata` 키로 지시문 생성 (예: `"pick up the {target_id} cube"`; 미지정 시 디코드된 라벨 값만)
   - 옵션 `--out <DIR>` (기본: 입력 옆 `lerobot/`), `--fps N` (기본 20), `--camera <name>`
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\h5_to_lerobot.py --traj-path "<PATH>" [--instruction "..."]
   ```
3. 출력 경로 + 요약(에피소드/프레임 수, tasks, action=10d 절대 EEF / state=qpos+eef) 보고.

## 출력 구조 (LeRobot v2.1 + modality.json)

```
<out>/
├── meta/{info.json, episodes.jsonl, tasks.jsonl, modality.json, stats.json}
├── data/chunk-000/episode_{i:06d}.parquet      # observation.state, action(10d 절대 EEF), 인덱스
└── videos/chunk-000/observation.images.<cam>/episode_{i:06d}.mp4
```

- 액션 = **10d 절대 EEF** `[eef_x,y,z, rot6d_0..5, gripper]` (`ActionFormat.XYZ_ROT6D`). 상태 = **`[qpos(Q), eef_abs(9)]`** — eef 블록이 상대화 기준(`state_key="eef"`). modality.json이 구간 매핑을 기록.
- 저장값은 **절대 pose**(`action[t]`=다음 스텝, `state[t]`=현재) — GR00T가 `rep=RELATIVE` 로 내부 상대화. 미리 델타를 만들지 않는다. rot6d는 회전행렬 첫 두 행(GR00T `pose.py` 컨벤션).
- 프레임 수 N = T-1; parquet 행수 == mp4 프레임수.
- 지시문은 env가 선언한 `label_metadata`에서 생성 — **task-무관** (스크립트에 task 이름 없음).

## 주의사항

- **먼저 `/ee_verify`로 EE 게이트 통과**를 권장 — EE+IK가 sim에서 재현되는지 확인 후 포장 (변환은 검증과 같은 `episode_joint_to_ee`를 쓰므로 같은 EE를 산출).
- 입력은 `--obs-mode rgb` 데이터셋이어야 함 (rgb + tcp_pose + qpos). 원본 `motionplanning.h5`는 안 됨.
- `codebase_version v2.1` 타깃. meta 스키마는 Isaac-GR00T 공식 예제(`demo_data/cube_to_bowl_5`)와 1:1 대조해 정합 확인됨 (info.json `info` 블록, modality `annotation.original_key="task_index"`, stats `q01/q99`).
- **stats**: 로더가 `stats.json` 존재를 요구(assert)하므로 valid한 형식(min/max/mean/std/q01/q99)으로 써둔다. 단 **학습 전 GR00T env에서 `python scripts/repair_lerobot_metadata.py <out> --embodiment-tag <tag>`** 로 `stats.json` + `relative_stats.json`(EEF 상대 액션 정규화용)을 재생성하는 게 정석 — repair는 info.json 카운트도 보정한다. `relative_stats.json`은 로더상 선택.
- **GR00T 측 설정**: modality 키(state: `qpos`/`eef`, action: `eef`/`gripper`)는 새 임베디먼트 data_config와 짝 — action `eef`는 `type=EEF, rep=RELATIVE, format=XYZ_ROT6D, state_key="eef"`, gripper는 `NON_EEF/ABSOLUTE`. `finetune_new_embodiment` 참고(데이터셋이 아니라 학습 박스 설정).
- 같은 `--out`에 재실행 시 덮어씀.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/h5_to_lerobot <hdf5>` | 전체 변환, 지시문=디코드 라벨 |
| `/h5_to_lerobot <hdf5> --instruction "pick up the {target_id} cube"` | 자연어 지시문 |
| `/h5_to_lerobot <hdf5> --out data/datasets/X/lerobot --fps 20` | 출력 위치·fps 지정 |

보통 흐름: `/h5_add_images` → `/h5_report` → `/ee_verify`(게이트) → **`/h5_to_lerobot`(포장)** → GR00T 학습(클라우드).
