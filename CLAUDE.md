# ManiSkill 하네스

[ManiSkill3](https://www.maniskill.ai) 위에 얹은 Windows용 데이터셋 생성 하네스. 로봇 팔 시뮬레이션 데모를 받아서, 리플레이로 (이미지 + 액션) 시퀀스 데이터셋을 만들고, 결과를 시각/구조 양쪽으로 검증할 수 있게 정리한 도구 모음.

다섯 가지 작업을 **슬래시 커맨드 / Python 함수 / CLI / 노트북** 네 가지 인터페이스에서 동일하게 호출할 수 있게 설계됨.

## 다섯 가지 스킬

| 슬래시 | 기능 | 스크립트 |
|---|---|---|
| `/setup` | Hugging Face에서 태스크 데모 다운로드 (멱등) | `scripts/setup.py` |
| `/generate` | 데모를 리플레이해서 RGB + 액션 HDF5 데이터셋 생성 | `scripts/generate.py` |
| `/check` | 환경 헬스체크 또는 생성된 HDF5 구조 검증 | `scripts/check.py` |
| `/render` | HDF5 → MP4 영상 / PNG 그리드 미리보기 추출 | `scripts/render.py` |
| `/live` | SAPIEN 뷰어 창 열기 — 환경 둘러보기 또는 에피소드 리플레이 | `scripts/live.py` |

Python 함수 진입점:

| 모듈 | 함수 |
|---|---|
| `scripts.setup` | `run(task, force=False)` |
| `scripts.generate` | `run(task, count, obs_mode, target_control_mode, num_envs, ...)` |
| `scripts.check` | `install()`, `dataset(path)` |
| `scripts.render` | `video(traj, episode, ...)`, `preview(traj, n, ...)` |
| `scripts.live` | `browse(task, ...)`, `replay(traj, episode, ...)` |

각 스크립트는 `if __name__ == "__main__":` 진입점에 동등한 argparse CLI가 있음.

## 디렉토리 구조

```
maniskill/
├── .claude/skills/     슬래시 커맨드 정의 (SKILL.md per 스킬)
├── scripts/            Python 스킬 모듈 (function + CLI 이중 인터페이스)
├── notebooks/          스킬별 테스트 노트북 (호출 패턴 예제 + smoke 검증)
├── data/               생성된 데이터셋/미디어 (gitignore, 재생성 가능)
│   └── datasets/<task>/
├── CLAUDE.md           이 파일
└── README.md           일반 소개
```

상태 분리 원칙 (자기 포함 / 재현 가능):

- **데모 (입력)** — ManiSkill 기본 캐시 `~/.maniskill/demos/<task>/` (프로젝트 밖). 외부 다운로드물이고 `/setup`으로 언제든 재생성되므로 프로젝트 밖에 둬도 재현성에 문제 없음.
- **생성물 (출력)** — `scripts/generate.py`가 만든 데이터셋, `scripts/render.py`가 만든 MP4/PNG는 모두 프로젝트 내부 `data/` 에 저장됨. 외부 데모 폴더는 절대 오염시키지 않음. `data/` 는 gitignore 대상 — 대용량이고 `git clone → /setup → /generate` 로 재생성 가능하므로 git엔 *레시피*만 들어가고 데이터 자체는 안 들어감.

## 환경 가정

- Windows 11 + NVIDIA GPU
- conda env: `maniskill`
- Python 실행 경로: `C:\Users\hun41\miniconda3\envs\maniskill\python.exe`
- 시뮬과 렌더 모두 **CPU 백엔드** 사용 (`sim_backend='cpu'`, `render_backend='cpu'`)
- 주요 패키지: `mani_skill 3.0.1`, `sapien 3.0.3`, `torch 2.12.0+cpu`, `jupyter`, `imageio[ffmpeg]`, `h5py`, `gymnasium`

`pinocchio`는 설치돼 있지 않음. EE 공간 컨트롤(`pd_ee_delta_pose`)과 텔레오퍼레이션은 이 의존성 위에 동작하므로 현재 미지원.

## 데이터 흐름

```
/setup <task>                          # Hugging Face → ~/.maniskill/demos/<task>/
        ↓ trajectory.h5 (원본 데모, pd_joint_pos)
/generate <task> <count>               # CPU 시뮬에서 리플레이하며 관측 새로 기록
        ↓ trajectory.<obs>.<ctrl>.<sim>.h5  (생성된 데이터셋)
/check dataset <hdf5>                  # 구조/통계 자동 검증
/render video|preview <hdf5> ...       # 영상/이미지 추출 (파일 출력)
/live browse|replay <task|hdf5> ...    # 데스크탑 뷰어 창
```

## 출력 파일 명명 규칙

`scripts/generate.py`는 프로젝트 내부 `data/datasets/<task>/` 에 다음 형식으로 저장:

```
data/datasets/<task>/trajectory.<obs_mode>.<control_mode>.<sim_backend>.h5
```

예: `data/datasets/PickCube-v1/trajectory.rgb.pd_joint_pos.physx_cpu.h5`. 같은 옵션으로 재실행하면 덮어씀.

내부 동작: `replay_trajectory`는 입력 데모 옆(외부 캐시)에 파일을 쓰는데, `generate.py`가 이를 곧바로 `data/datasets/<task>/` 로 이동시킴 (`.h5` + `.json`). 따라서 외부 캐시엔 생성물이 남지 않음.

## 코드 작성 시 유지해야 할 부분

- `scripts/generate.py`와 `scripts/live.py`의 `gym.make` monkey-patch — `render_backend='cpu'` 기본값 주입. Windows GPU 렌더 경로가 동작 불가능하므로 이 우회 필요.
- `scripts/generate.py`의 `if __name__ == "__main__":` 가드 — Windows multiprocessing은 `spawn` 방식이라 가드가 없으면 자식 프로세스가 무한 spawn 루프에 빠짐.
- 함수 인터페이스와 CLI 인터페이스의 동등성 — 새 옵션 추가 시 양쪽에 일관되게 반영.
