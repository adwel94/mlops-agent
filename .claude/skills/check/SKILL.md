---
name: check
description: ManiSkill 하네스의 자동 헬스체크. 두 모드 — `install` (imports + CPU 시뮬 + 렌더 정상 동작 검증, 약 10초) 또는 `dataset PATH` (생성된 HDF5가 VLA 스타일의 에피소드/RGB/액션 구조를 갖췄는지 검증). 환경 변경 후 "다 정상이야?" 빠른 확인, 또는 데이터셋 생성 후 결과 유효성 확인 시 사용. args는 `install` 또는 `dataset <hdf5-경로>` 로 파싱; 비어있으면 `install` 기본값.
---

# Check 스킬 — 환경 / 데이터셋 검증

`scripts/check.py` 래퍼. 항목별 PASS/FAIL과 전체 판정 반환.

## 호출됐을 때

1. `args` 파싱:
   - `install` (기본) → 환경 헬스체크
   - `dataset <PATH>` → HDF5 파일 구조 검증
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\check.py --install
   ```
   또는
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\check.py --dataset "<PATH>"
   ```
3. 전체 PASS/FAIL 표 + 종합 판정 그대로 보여주기. 종료 코드: 0 = pass, 1 = fail.

## install 모드 — 무엇을 검사하나

- imports: `mani_skill`, `sapien`, `gymnasium`, `h5py`, `torch`, `PIL`
- CUDA 가용성 (참고용; 현재 환경은 `torch+cpu` 라서 `False`)
- PickCube-v1 환경 construct + reset (CPU 시뮬/렌더)
- CPU 백엔드로 단일 프레임 RGB 렌더
- 다운로드된 데모 존재 여부

## dataset 모드 — 무엇을 검사하나

- 파일 존재, HDF5 읽기 가능
- 최소 1개 이상의 `traj_*` 에피소드
- 각 에피소드의 `actions`, `obs`, `success` 그룹 존재
- RGB 프레임 shape이 에피소드 전체에서 일관됨
- 에피소드 종료 시점 성공률

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/check` | 환경 헬스체크 |
| `/check install` | 동일 |
| `/check dataset C:\Users\hun41\.maniskill\demos\PickCube-v1\motionplanning\trajectory.rgb.pd_joint_pos.physx_cpu.h5` | 데이터셋 구조 검증 |
