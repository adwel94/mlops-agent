---
name: fetch
description: 주어진 ManiSkill 태스크 ID의 공식 데모 파일을 Hugging Face에서 다운로드 (액션 공급원 중 "받아오기" 경로). 멱등 동작 — 이미 받아져 있으면 스킵. 직접 액션을 생성하는 solve의 빠른 대안/베이스라인으로, 데이터셋 생성 전 기성 데모가 필요할 때 사용 (태스크당 1회). args는 `[태스크-ID] [--force]` 형식의 자유 문자열로 파싱; 비어있으면 `PickCube-v1` 기본값.
---

# Fetch 스킬 — 공식 ManiSkill 데모 다운로드

이 프로젝트의 `scripts/fetch.py` 래퍼. ManiSkill 공식 Hugging Face 데모 번들을 `~/.maniskill/demos/<task>/` 경로에 다운로드한다.

`fetch`는 **액션 공급원(producer)** 두 개 중 하나다. `solve`(WSL 모션플래닝)가 액션을 처음부터 생성하는 반면, `fetch`는 기성 공식 데모를 받아온다 — 빠르고 베이스라인용. 둘 다 같은 형식(액션 + env_states, 이미지 없음)을 만들고, 이후 `generate`가 리플레이하며 RGB를 입힌다.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 비-플래그 토큰 = 태스크 ID (기본 `PickCube-v1`)
   - `--force` 가 어디든 있으면 = 이미 있어도 재다운로드
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\fetch.py --task <TASK> [--force]
   ```
   PowerShell 툴 사용. `Set-Location C:\Users\hun41\PycharmProjects\maniskill;` 후 명령 실행.
3. 스크립트가 출력한 마지막 2~3줄 그대로 돌려주기: `[fetch] <task>: already present -> <path>` 또는 다운로드 진행 + `Demos ready -> <path>`.

## 참고

- 데모는 `C:\Users\hun41\.maniskill\demos\<task>\` 에 저장됨 (프로젝트 디렉토리 밖 — 외부 다운로드물이라 재현 가능, 자기 포함 원칙 위배 아님).
- `PickCube-v1`은 하네스 구축 시점에 이미 받아져 있음.
- Hugging Face (`haosulab/ManiSkill_Demonstrations`)에서 태스크당 약 30~40 MB.
- 반환값은 디렉토리 경로. 사용자가 보통 원하는 HDF5는 `<demos>/<task>/motionplanning/trajectory.h5`.

## 예시

| 사용자 입력 | 동작 |
|---|---|
| `/fetch` | PickCube-v1 다운로드 (없는 경우) |
| `/fetch StackCube-v1` | StackCube-v1 다운로드 (없는 경우) |
| `/fetch PickCube-v1 --force` | 이미 있어도 재다운로드 |
