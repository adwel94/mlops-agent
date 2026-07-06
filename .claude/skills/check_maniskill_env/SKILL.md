---
name: check_maniskill_env
description: ManiSkill 하네스 환경이 "이 환경에서 하네스가 돌아가나?"를 검증하고, 고칠 수 있는 건 고치고(--fix 로 requirements.txt 설치) 못 하는 건 정확한 다음 단계로 제안하는 스킬. 핵심 import + CPU 시뮬 + CPU 렌더 + (베스트에포트) WSL mplib 를 점검한다. 환경을 바꾼 뒤 정상 확인, 또는 무언가 깨졌을 때 "환경 문제"인지 "데이터/코드 문제"인지 가를 때 사용. args = `[--fix] [--no-wsl]`.
---

# check_maniskill_env — 환경 검증 + 복구

`scripts/check_maniskill_env.py` 래퍼. 다른 모든 스킬이 의존하는 부분을 점검하고 —
단순 판정에 그치지 않고 **고칠 수 있는 건 고치고, 못 하는 건 정확한 명령으로 제안**한다.

- ✅ **직접 고침** (`--fix`): 누락 pip 패키지 → `requirements.txt`(단일 출처)를 읽어 설치.
  버전 핀은 이 스크립트가 아니라 requirements.txt 에 있고, 스킬은 그걸 **실행**한다.
- 🔶 **못 함 → 제안**: WSL(mplib·mesa-vulkan) · conda env 생성 자체 · `.env` 시크릿은
  이 스킬(그 env 안에서 돎)이 실행 못 함 → `SETUP.md` 를 가리켜 다음 단계를 제안.

(데이터셋 구조 검증은 여기 없음 — 생성 시점에 확인된다.)

## 호출됐을 때

1. `args` 파싱: `--fix`(복구 실행), `--no-wsl`(WSL 프로브 건너뜀, Windows 전용 파이프라인).
   - 기본(플래그 없음) = **검증만 + 제안**. 설치는 `--fix` 로만 (플래그가 곧 승인 —
     CLAUDE.md "패키지 설치 먼저 승인" 정합).
2. 프로젝트 루트에서 실행:
   ```
   <maniskill-python> scripts/check_maniskill_env.py [--fix] [--no-wsl]
   ```
3. PASS/WARN/FAIL 표 + 각 비-PASS 항목의 `→ 제안` + 종합 판정 그대로 보고.
   종료 코드: 0 = pass, 1 = fail.

## 무엇을 검사하나

- **core imports**: `mani_skill`, `sapien`, `gymnasium`, `h5py`, `torch`, `PIL` (FAIL = 게이트)
- **extras** (WARN): `pyarrow`, `imageio` — `h5_to_lerobot`·`h5_report` 에만 필요
- **CPU 시뮬**: PickCube-v1 construct + reset
- **CPU 렌더**: 단일 프레임 RGB
- **wsl_mplib** (WARN): WSL 에서 `import mplib` — `task_to_h5`·`ee_verify`·`gr00t_eval` 에만 필요.
  WSL 미설치/미완이면 WARN(전체 FAIL 아님) + SETUP.md 제안.

`--fix` 는 core/extras 가 빠졌을 때 `pip install -r requirements.txt` 를 현재 인터프리터 env 에
실행하고 재검사한다. WSL·env생성·시크릿은 스스로 못 하니 항상 제안만.

## 최초 1회 (부트스트랩)

conda env 자체가 없으면 스킬이 돌 수도 없다(그 env 안에서 실행되므로). 한 줄만 먼저:
`conda create -n maniskill python=3.10` → 그 다음부터 `--fix` 가 나머지를 채운다. 전체 절차는 SETUP.md.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/check_maniskill_env` | 검증만 — PASS/WARN/FAIL + 제안 |
| `/check_maniskill_env --fix` | 누락 pip 패키지를 requirements.txt 로 설치 후 재검증 |
| `/check_maniskill_env --no-wsl` | WSL 프로브 생략(Windows 전용 파이프라인) |
