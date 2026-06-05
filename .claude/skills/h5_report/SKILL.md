# h5_report — 데이터셋 품질 리포트 (Markdown)

`scripts/h5_report.py` 래퍼. 이미지가 입혀진 데이터셋 HDF5(`h5_add_images` 출력)에서 **랜덤 N개 에피소드**를 뽑아, 각각 **메타데이터 표 + 인라인 필름스트립(PNG) + MP4 링크**를 담은 Markdown 리포트를 생성한다. 숫자로는 안 보이는 (이미지 + 지시 + 행동) 정렬을 사람이 눈으로 검증하는 **학습 전 가드레일**.

시뮬레이터는 안 돈다 — HDF5에 이미 기록된 RGB 프레임만 읽어 조립. `scripts/h5_to_media.py`의 재사용 렌더러(`card`/`video`)를 호출한다.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 토큰 = HDF5 경로 (RGB가 기록된 `h5_add_images` 출력 — 옆에 `.json` 사이드카 필요). **필수.**
   - 두 번째 정수 토큰 = 에피소드 수 (기본 `3`)
   - 옵션 `--seed N` (재현 가능한 랜덤 선택), `--fps N` (영상 fps, 기본 15)
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\h5_report.py --traj-path "<PATH>" --n 3 [--seed 42]
   ```
3. 생성된 `.md` 경로 보고. 리포트와 자산(PNG/MP4)은 입력 옆 `reports/` 폴더에 저장됨. 필름스트립 PNG는 Read 툴로 사용자에게 인라인 표시 가능.

## 동작 / 주의사항

- 입력 HDF5는 `--obs-mode rgb`로 만들어졌어야 함 (`sensor_data/<cam>/rgb` 존재). 없으면(원본 `motionplanning.h5` 등) 명확한 에러 — 먼저 `/h5_add_images`로 이미지를 입힐 것.
- **task-무관**: 지시문/라벨은 데이터셋 `.json`의 `label_metadata`(env가 선언)를 디코드해 표시 (예: `target_id=red`). `label_metadata`가 없는 task는 라벨 칸이 비고 카드 제목이 단순해질 뿐, 그대로 동작.
- 메타 표 항목: instruction(디코드), success, steps(액션 수), seed, action/state dim. 리포트 헤더엔 전체 성공률도 표기.
- 필름스트립 카드: 프레임 테두리 = 그리퍼 상태 best-effort(qpos 마지막 차원을 에피소드 내 정규화 — 초록=열림/빨강=닫힘). 매직 넘버 없음.
- 출력은 멱등이 아님 — 같은 `--seed`면 같은 에피소드를 뽑아 덮어씀. seed 없으면 매번 랜덤.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/h5_report data/datasets/PickCube-v1/trajectory.rgb.pd_joint_pos.physx_cpu.h5` | 랜덤 3개 에피소드 리포트 |
| `/h5_report <hdf5> 5` | 랜덤 5개 |
| `/h5_report <hdf5> 3 --seed 42` | 재현 가능한 랜덤 3개 |

보통 흐름: `/h5_add_images <태스크> <N>` → `/h5_report <그 출력 h5> 3` 으로 품질 점검 → (이후) LeRobot 변환.
