---
name: render
description: 저장된 trajectory HDF5에서 정적 미디어(한 에피소드의 MP4 영상 또는 여러 에피소드 프레임의 PNG 그리드)를 추출. 순수 파일 읽기 — 시뮬레이터 실행 없음. 데스크탑 뷰어를 열지 않고 생성된 데이터셋의 내용을 시각적으로 점검할 때 사용. args는 `video|preview <hdf5-경로> [에피소드|개수]` 형식; 경로 미지정 시 PickCube-v1 RGB 기본 출력 경로 사용.
---

# Render 스킬 — 미디어 추출

`scripts/render.py` 래퍼. 두 서브커맨드.

## 호출됐을 때

1. `args` 파싱:
   - 첫 번째 토큰: `video` 또는 `preview` (기본 `video`)
   - 두 번째 토큰: HDF5 경로 (기본 `C:\Users\hun41\.maniskill\demos\PickCube-v1\motionplanning\trajectory.rgb.pd_joint_pos.physx_cpu.h5`)
   - 세 번째 토큰: 정수
     - `video` 의 경우 → 에피소드 인덱스 (기본 `0`)
     - `preview` 의 경우 → 그리드 에피소드 수 (기본 `9`)
   - 옵션 `--fps N`, `--frame first|mid|last`, `--camera NAME`, `--out PATH`
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\render.py video --traj-path "<PATH>" --episode N
   ```
   또는
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\render.py preview --traj-path "<PATH>" --n N
   ```
3. 출력 파일 경로와 크기 보고. 만든 PNG는 Read 툴로 사용자에게 인라인으로 보여줄 수 있음.

## 참고

- 원본 HDF5가 `--obs-mode rgb` 로 생성됐어야 함 (즉 `sensor_data/<cam>/rgb` 존재). 없으면 스크립트가 명확한 에러 발생.
- 기본 출력 이름: 원본과 같은 디렉토리에 `<source-stem>.ep<NNNN>.mp4` 또는 `<source-stem>.preview_<frame>_<N>.png`.
- MP4 인코딩은 imageio + ffmpeg (환경에 이미 설치돼 있음). 빠름.
- PNG 그리드는 정사각형에 가까운 비율 (ceil(sqrt(N)) 열).

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/render video` | 기본 HDF5의 0번 에피소드 MP4 |
| `/render video PATH 5` | PATH의 5번 에피소드 MP4 |
| `/render preview PATH 9` | PATH의 3x3 중간 프레임 그리드 |
| `/render preview PATH 16 --frame last` | 4x4 마지막 프레임 그리드 |
