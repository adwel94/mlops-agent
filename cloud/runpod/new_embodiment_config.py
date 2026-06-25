"""GR00T NEW_EMBODIMENT modality config — h5_to_lerobot 출력과 1:1.

`launch_finetune.py --modality-config-path` 가 이 파일을 **import** 하고, import
side-effect 로 `register_modality_config(...)` 가 호출되어 등록된다
(Isaac-GR00T `gr00t/experiment/launch_finetune.py` 의 `load_modality_config` 계약).

modality_keys 는 우리 데이터셋 `meta/modality.json` 의 키와 정확히 일치해야 한다:
    state : qpos, eef
    action: eef, gripper
    video : base_camera
    annotation: human.task_description
"""

from gr00t.configs.data.embodiment_configs import register_modality_config
from gr00t.data.embodiment_tags import EmbodimentTag
from gr00t.data.types import (
    ActionConfig,
    ActionFormat,
    ActionRepresentation,
    ActionType,
    ModalityConfig,
)

# GR00T-N1.7 의 액션 호라이즌 = 16. delta_indices 길이가 모델 액션 헤드와 맞아야 함.
ACTION_HORIZON = 16

config = {
    # 단일 카메라, 히스토리 없음(현재 프레임만).
    "video": ModalityConfig(
        delta_indices=[0],
        modality_keys=["base_camera"],
    ),
    # 상태 = [qpos(9), eef_abs(9)]. eef 블록이 EEF 액션의 상대화 기준(state_key).
    "state": ModalityConfig(
        delta_indices=[0],
        modality_keys=["qpos", "eef"],
    ),
    # 액션 = 10d [eef(9: xyz+rot6d), gripper(1)]. modality_keys 순서가 action_configs 와 정렬.
    "action": ModalityConfig(
        delta_indices=list(range(ACTION_HORIZON)),
        modality_keys=["eef", "gripper"],
        action_configs=[
            # 절대 EEF 를 저장 → GR00T 가 state_key="eef" 기준으로 내부 상대화.
            ActionConfig(
                rep=ActionRepresentation.RELATIVE,
                type=ActionType.EEF,
                format=ActionFormat.XYZ_ROT6D,
                state_key="eef",
            ),
            # gripper 는 절대값 그대로.
            ActionConfig(
                rep=ActionRepresentation.ABSOLUTE,
                type=ActionType.NON_EEF,
                format=ActionFormat.DEFAULT,
                state_key="gripper",
            ),
        ],
    ),
    # 언어 지시문(tasks.jsonl → task_index 로 매핑된 annotation).
    "language": ModalityConfig(
        delta_indices=[0],
        modality_keys=["annotation.human.task_description"],
    ),
}

register_modality_config(config, embodiment_tag=EmbodimentTag.NEW_EMBODIMENT)
print("[new_embodiment_config] registered NEW_EMBODIMENT modality config")
