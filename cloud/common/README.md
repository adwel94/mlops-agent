# cloud/common — 공유 파드 인프라

serve 이미지(`cloud/serve`)와 train 이미지(`cloud/train`)가 **둘 다 COPY**하는 공유 스크립트.
여기가 단일 출처 — 각 이미지 Dockerfile 이 부팅용으로 `/app` 에 COPY 한다.

| 파일 | 역할 |
|---|---|
| `bootstrap.sh` | 부팅 환경 셋업(apt·uv sync·GR00T clone, 멱등) + BOOT_PROFILE 계측 emit |
| `new_embodiment_config.py` | GR00T `NEW_EMBODIMENT` modality config — 카메라를 `modality.json` 에서 **동적 발견**(하드코딩 금지) |
| `utils/discord.py` | Discord **채널 정의**(`DiscordChannel` enum) + 전송 유틸 (채널 정의의 원천) |
| `_log_shipper.py` | 파드 stdout → Discord STDOUT 채널 시퍼 |

## 데이터셋 ↔ GR00T config 매핑

`new_embodiment_config.py` 의 `modality_keys` 는 데이터셋 `meta/modality.json` 키와 정확히 일치:

| | 키 | GR00T ActionConfig |
|---|---|---|
| state | `qpos`, `eef` | — (`eef` 가 상대화 기준 `state_key`) |
| action | `eef` | `EEF / RELATIVE / XYZ_ROT6D / state_key="eef"` |
| action | `gripper` | `NON_EEF / ABSOLUTE / DEFAULT` |
| video | `base_camera`(+발견된 카메라) | — |
| language | `annotation.human.task_description` | — |

액션 호라이즌 = 16 (`delta_indices=range(16)`, GR00T-N1.7 액션 헤드와 정합).
