"""scripts 패키지 공통 초기화 — 플랫폼 렌더 백엔드 지정.

macOS: sapien 은 Vulkan 로더만 번들하고 드라이버(ICD)는 시스템 것을 쓴다. Vulkan 로더는
/opt/homebrew 를 검색하지 않으므로 Homebrew MoltenVK 의 ICD 를 명시해야 렌더가 뜬다
(WSL 이 lavapipe ICD 를 VK_ICD_FILENAMES 로 강제하는 것과 같은 패턴 — task_to_h5.WSL_VK_ICD).
ICD 경로는 vkCreateInstance 시점(env 생성)에 읽히므로 sapien import 순서와 무관하게
이 패키지가 import 되는 시점이면 충분하다.
"""
import os
import sys

MAC_VK_ICD = "/opt/homebrew/etc/vulkan/icd.d/MoltenVK_icd.json"

if sys.platform == "darwin" and os.path.isfile(MAC_VK_ICD):
    os.environ.setdefault("VK_ICD_FILENAMES", MAC_VK_ICD)
