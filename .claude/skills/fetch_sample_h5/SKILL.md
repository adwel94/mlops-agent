---
name: fetch_sample_h5
description: 공식 ManiSkill 데모 궤적(.h5)을 Hugging Face에서 받아 프로젝트 data/datasets/<task>/trajectory.h5 로 저장. 행동 궤적을 직접 만드는 task_to_h5의 빠른 대안/베이스라인으로, ManiSkill이 데모를 배포하는 태스크에서만 가능. 멱등 — 이미 프로젝트에 있으면 스킵. args는 `[태스크-ID] [--force]` 형식의 자유 문자열로 파싱; 비어있으면 `PickCube-v1` 기본값.
---

# fetch_sample_h5 — 공식 데모 궤적 받기

`scripts/fetch_sample_h5.py` 래퍼. ManiSkill 공식 데모를 다운로드한 뒤 **프로젝트 안** `data/datasets/<task>/trajectory.h5` (+ `.json`) 로 복사한다. 이렇게 하면 행동 궤적이 (직접 생성한 `task_to_h5` 산출물과 같은 폴더에) 프로젝트 내부에 모여, 다음 단계(`h5_add_images`)가 한 곳만 보면 된다.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 비-플래그 토큰 = 태스크 ID (기본 `PickCube-v1`)
   - `--force` 가 있으면 = 이미 있어도 다시 받기
2. 프로젝트 루트에서 실행 (PowerShell 툴, `Set-Location C:\Users\hun41\PycharmProjects\maniskill;` 후):
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\fetch_sample_h5.py --task <TASK> [--force]
   ```
3. 마지막 출력 줄 그대로 보고: `[fetch_sample_h5] <task>: already in project -> <path>` 또는 다운로드 후 `Sample trajectory ready -> <path>`.

## 참고

- 산출물: `data/datasets/<task>/trajectory.h5`. "trajectory" stem 은 이게 받아온 데모임을 표시 (직접 생성한 건 "motionplanning").
- 다운로드 자체는 ManiSkill이 외부 캐시(`~/.maniskill/demos/`)에 받고, 이 스킬이 프로젝트로 복사한다.
- ManiSkill이 데모를 배포하는 태스크만 가능. 데모가 없는 태스크는 `task_to_h5` 로 직접 생성.
- 이 궤적을 데이터셋으로 만들려면: `/h5_add_images <태스크> --traj-path data/datasets/<태스크>/trajectory.h5`.

## 예시

| 사용자 입력 | 동작 |
|---|---|
| `/fetch_sample_h5` | PickCube-v1 데모를 프로젝트로 받기 |
| `/fetch_sample_h5 StackCube-v1` | StackCube-v1 데모 받기 |
| `/fetch_sample_h5 PickCube-v1 --force` | 이미 있어도 다시 받기 |
