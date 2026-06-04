---
name: check_maniskill_env
description: ManiSkill 하네스 설치/환경이 정상 동작하는지 자동 헬스체크 (핵심 import + CPU 시뮬 + CPU 렌더, 약 10초). 환경을 바꾼 뒤 "다 정상이야?" 를 빠르게 확인하거나, 무언가 깨졌을 때 "환경 문제"인지 "데이터/코드 문제"인지 가를 때 사용. 파라미터 없음.
---

# check_maniskill_env — 환경 헬스체크

`scripts/check_maniskill_env.py` 래퍼. 다른 모든 스킬이 의존하는 부분(import, CPU 시뮬, CPU 렌더 경로)을 점검하고 항목별 PASS/FAIL + 종합 판정을 반환한다.

(데이터셋 구조 검증은 여기 없음 — 생성 시점에 확인되고, 더 깊은 목적별 검증은 추후 학습 정제 단계의 몫이다.)

## 호출됐을 때

1. `args` 없음.
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\check_maniskill_env.py
   ```
3. PASS/FAIL 표 + 종합 판정 그대로 보고. 종료 코드: 0 = pass, 1 = fail.

## 무엇을 검사하나

- imports: `mani_skill`, `sapien`, `gymnasium`, `h5py`, `torch`, `PIL`
- CUDA 가용성 (참고용; 현재 환경은 `torch+cpu` 라 `False`)
- PickCube-v1 환경 construct + reset (CPU 시뮬/렌더)
- CPU 백엔드로 단일 프레임 RGB 렌더

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/check_maniskill_env` | 환경 헬스체크 실행 |
