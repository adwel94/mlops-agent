# Mac 마이그레이션 플랜 — GR00T 모델을 Mac 에서 직접 실행

파인튜닝된 GR00T 정책을 **Mac(Apple Silicon) 에서 네이티브로** 롤아웃/인터랙티브 사용하기
위한 이행 계획. 지금은 sim+IK 롤아웃이 Windows→WSL 로 우회하는데, WSL 이 필요한 유일한
이유(mplib 이 Linux 전용)를 Mac 에선 **pinocchio 로 대체**해 WSL 없이 한 env 에서 돌린다.

> **이 문서는 Mac 의 Claude Code 세션이 실행할 스펙이다.** Windows 쪽에서 코드 분석만으로
> 작성했고 Mac 에서 검증하진 않았다(여기선 mplib·MoltenVK 를 못 돌린다). 아래 파일:라인 참조와
> §9 검증 게이트를 그대로 실행 근거로 삼되, 실제 API 시그니처(pinocchio·ManiSkill 컨트롤러)는
> Mac 에서 import 해 확인하며 진행할 것. 착수 순서는 §8 체크리스트.

## 0. 목표·범위

- **목표** — Mac 에서 `gr00t_eval` 롤아웃을 네이티브로 실행. sim 이 매 스텝 카메라 RGB 를
  렌더(MoltenVK)해 모델에 먹이고, 모델의 EE 출력을 IK 로 풀어 실행한다.
- **정책(GPU)은 변화 없음** — GR00T-3B 는 지금도 로컬에서 돈 적 없다. 계속 RunPod 원격
  ZMQ 서버(5555)로 서빙하고, Mac 은 그 클라이언트(sim+IK+렌더)만 맡는다.
- **범위 밖** — 새 데이터셋 생성(`task_to_h5` 의 모션플래닝). mplib *플래너*(단순 IK 가 아니라
  충돌회피 경로계획)에 의존하고 pinocchio 는 플래너가 아니라 Mac 에서 대체가 안 된다(§6).

## 1. 근거 — 왜 지금 WSL 이 필요하고, Mac 에선 무엇이 바뀌나

| 항목 | 현재(Windows+WSL) | Mac |
|---|---|---|
| IK | mplib `planner.IK` (Linux 전용) → WSL | **pinocchio** (osx-arm64 지원) — 네이티브 |
| 렌더 | WSL 소프트웨어 Vulkan(lavapipe) | SAPIEN Vulkan→**MoltenVK** (공식 지원) |
| 병렬 env(GPU sim) | 안 씀(`sim_backend="cpu"`) | 못 씀(CUDA 없음) — 그런데 **애초에 안 씀** |
| 정책(GPU) | RunPod 원격 | RunPod 원격(동일) |

ManiSkill 공식 문서: macOS 는 **CPU sim + 렌더 지원**, 못 하는 건 `physx_cuda`(GPU 병렬
sim)뿐 — 우리가 안 쓰는 그것. 그래서 이행의 실질 관문은 **mplib IK → pinocchio** 하나다.

## 2. 핵심 관문 — mplib IK 를 pinocchio 로 대체

mplib 호출은 코드 전체에서 **단 한 지점**이다:

- `scripts/ik_exec.py:98` — `status, qsol = solver.planner.IK(goal, ref_q)` (mplib IK).
- 이걸 감싸는 `solve_to_arm(...)` 를 `_wsl_gr00t_eval.py:269` 와 `_wsl_ee_verify.py` 가 공유.

eval 실행 루프(`_wsl_gr00t_eval.py:261-272`)의 나머지는 전부 순수 numpy/sapien:

```
action["eef"] (H,9 = xyz+rot6d)  →  rot6d_to_quat  →  world target pose (tp, tq)
  →  solve_to_arm(...)  =  [여기만 mplib]  →  arm7
  →  env.step([arm7, gripper])   (control_mode="pd_joint_pos")
```

즉 **`solve_to_arm` 의 IK 백엔드만 갈아끼우면** 나머지 파이프라인·제어모드·`env.step`·성공
판정이 그대로 유지된다.

### 대체안

- **[권장] Option B — `ik_exec` 에 pinocchio IK 백엔드 추가 (drop-in).**
  - `control_mode="pd_joint_pos"` 유지, `env.step` 유지. `solve_to_arm` 내부만 pinocchio 의
    damped-least-squares IK 로 교체(Panda URDF 로 model 빌드, `last_q` 시드, base 프레임 목표,
    관절한계 클램프). 목표 pose 가 매 스텝 작게 움직여(시드 근처) 몇 iter 로 수렴.
  - **장점**: 변경 반경 최소(ik_exec 한 파일). 실행 동역학·성공판정 동일 → **거동 파리티**.
    mplib 경로는 Windows/WSL 용으로 그대로 남기고, **가용성으로 백엔드 선택**(darwin→pinocchio,
    linux→mplib). 기존 `ee_verify` 게이트가 그대로 이 IK 를 검증(§9).
  - **단점**: IK 솔버를 우리가 작성·튜닝(수렴·분기선택). 단 `ee_verify` 가 정확히 그 테스트
    하네스라 리스크가 관리된다.

- **Option A — ManiSkill 네이티브 `pd_ee_pose` 컨트롤러 사용(내부적으로 pinocchio).**
  - env 를 `control_mode="pd_ee_pose"` 로 만들고 모델의 절대 EE 목표를 base 프레임으로 바꿔
    액션으로 직접 투입. IK 를 ManiSkill 이 내부 처리(우리 IK 코드 0).
  - **장점**: 커스텀 IK 코드 없음. CLAUDE.md 가 말한 "pinocchio = pd_ee_delta_pose 의존"의 그 경로.
  - **단점**: 제어모드가 바뀌면 컨트롤러 내부 보간/PD 로 **실행 동역학이 달라져** 성공률이
    기존 mplib 기반과 어긋날 수 있다 → 전면 재검증 필요. `ee_verify` 게이트의 의미도 재정의.

> **결정: Option B 로 진행**(파리티·최소변경). Mac 세션은 B 로 착수한다. B 의 pinocchio IK 가
> §9 의 `ee_verify` 파리티 게이트를 통과 못 하면(수렴 실패·정확도 미달) 그때 A 로 전환한다.

## 3. WSL 오케스트레이션 제거 (Mac = 인프로세스)

`gr00t_eval.py` 는 지금 `wsl.exe -d <distro> -- bash -lc ...` 로 WSL child 를 띄우고,
경로를 `_win_to_wsl` 로 변환하고, `VK_ICD_FILENAMES=lavapipe` 를 강제한다(`gr00t_eval.py:91,114-118`).
Mac 에선 이 계층이 전부 불필요 — 같은 conda env 안에서 `_wsl_gr00t_eval.py` 로직을
**직접 import·호출**한다.

- `scripts/gr00t_eval.py` `run(...)` 에 플랫폼 분기: `sys.platform == "darwin"`(또는 linux
  네이티브) → 인프로세스 실행; `win32` → 기존 wsl.exe 경로 유지.
- MoltenVK 는 sapien 이 자동 선택(별도 ICD 강제 불필요). lavapipe 강제는 Windows/WSL 전용.
- cp949 회피용 `sys.stdout.reconfigure(utf-8)`(`gr00t_eval.py:32-36`)는 Mac 에선 무해(그대로 둠).

## 4. 플랫폼 결합 지점 인벤토리 (손볼 파일)

| 파일 | 결합 | Mac 조치 |
|---|---|---|
| `scripts/ik_exec.py` | mplib `planner.IK` | pinocchio 백엔드 추가(§2) |
| `scripts/gr00t_eval.py` | wsl.exe·`_win_to_wsl`·VK_ICD | darwin→인프로세스 분기(§3) |
| `scripts/ee_verify.py` | 위와 동일(WSL 오케스트레이션) | darwin→인프로세스 분기(검증 게이트가 Mac 에서도 돌아야 함) |
| `scripts/task_to_h5.py` | `WSL_DISTRO/WSL_PYTHON/WSL_VK_ICD`·모션플래닝 | 범위 밖(§6); 상수는 Windows 전용으로 남김 |
| `requirements.txt` | `mplib/pyzmq/msgpack`이 `sys_platform=="linux"` 로만 | darwin 마커 추가(§7) |
| `scripts/check_maniskill_env.py` | 플랫폼 가정 | darwin 인지(pinocchio 확인, mplib 미요구) |
| `SETUP.md` | Windows/WSL 절차만 | Mac 섹션 추가(§7) |
| `CLAUDE.md`·`README.md` | 환경 가정 서술 | Mac 실행경로 반영(문서, 마지막) |

> `_wsl_*` 접두 스크립트명은 이제 "Linux/네이티브 롤아웃 러너"라는 의미로 넓어진다. 파일명
> 대량 리네임은 리스크라 **이번엔 건드리지 않음**(동작 우선, 이름은 후속 정리).

## 5. 그대로 포팅되는 것 (변경 없음/사소)

`sapien==3.0.3` + `mani_skill==3.0.1` 이 osx-arm64 에서 설치·렌더되면 아래는 순수 파이썬/CPU:

- `h5_add_images`(SAPIEN CPU 렌더), `h5_report`, `h5_to_lerobot`, `hf_push_dataset`
- `view_task`·`replay_h5`(SAPIEN 뷰어 — 약한 GPU 는 FPS 낮음, 공식 주의)
- 클라우드 스킬 전체(`runpod_*`·`gr00t_train`·`gr00t_serve`) — RunPod API 호출, 플랫폼 무관
- ZMQ/msgpack 클라이언트 프로토콜 — 서버와 동일

## 6. 포팅 안 되는 것 (정직)

- **`task_to_h5` (새 데이터셋 생성)** — mplib 의 **모션 플래너**(충돌회피 경로계획)에 의존.
  pinocchio 는 IK/동역학이지 플래너가 아니라 Mac 대체 불가. 새 궤적 생성이 필요하면 Linux
  박스/클라우드에서 하거나 Windows+WSL 을 유지한다. **현재 목표(모델 실행)엔 불필요** —
  데이터셋은 이미 생성돼 있다.

## 7. Mac 환경 셋업 (SETUP.md 에 추가)

```bash
# 1) conda env (osx-arm64, Python 3.10)
conda create -n maniskill python=3.10 -y
conda activate maniskill

# 2) IK: pinocchio (conda-forge 가 가장 안정적; pip `pin` 도 가능)
conda install -c conda-forge pinocchio -y

# 3) 나머지 pip 의존성 (sapien/mani_skill/torch-cpu/zmq/msgpack)
pip install -r requirements.txt

# 4) 검증
python scripts/check_maniskill_env.py
```

`requirements.txt` 마커 수정(단일 출처):

```
# 현재: linux 에서만 → Mac 클라이언트가 서버와 통신 못 함. darwin 도 포함.
pyzmq;        sys_platform == "linux" or sys_platform == "darwin"
msgpack;      sys_platform == "linux" or sys_platform == "darwin"
msgpack-numpy;sys_platform == "linux" or sys_platform == "darwin"
mplib;        sys_platform == "linux"          # 여전히 Linux 전용
# pinocchio 는 conda-forge 로 설치(pip `pin` 도 가능) — pip 라인은 선택.
```

## 8. 실행 체크리스트 (Mac 에서 순서대로)

1. §7 로 env 구성 → `check_maniskill_env` 통과(pinocchio import OK, SAPIEN 렌더 OK).
2. SAPIEN 렌더 스모크: `python scripts/view_task.py <task>` 또는 작은 `h5_add_images` 로
   MoltenVK 렌더 확인(창 없이 rgb_array 로도 가능).
3. IK 백엔드 확정(§2 Option B) 후 `ik_exec` pinocchio 경로 구현.
4. **파리티 게이트**: `ee_verify` 를 Mac 인프로세스로 실행 → 기록 EE 델타 재현 오차가
   Windows/WSL mplib 결과와 동등(허용오차 내)인지 확인(§9).
5. RunPod 에 정책 서빙(`/gr00t_serve <repo>`), `publicIp`+5555 포트 획득.
6. `gr00t_eval` 을 Mac 에서 `--count 3` 소량 실행 → 서버 왕복·롤아웃·성공판정 동작 확인.
7. 필요 시 전체 eval.

## 9. 검증 게이트 (거동이 안 깨졌다는 증거)

- **1차 — `ee_convert` 라운드트립**: 이미 순수 numpy, Mac 에서 그대로 통과해야 함(좌표규약 무결).
- **2차 — `ee_verify` 파리티**: recorded EE 델타 → pinocchio IK 재현 → pose 오차가 mplib 기준과
  동등. 이게 IK 대체의 **핵심 합격선**. `ee_verify` 는 원래 이 목적의 게이트다.
- **3차 — 소량 eval**: 같은 모델·시드로 Mac(pinocchio) vs 기존(WSL mplib) 성공/anypick 이
  통계적으로 비슷하면 실행 동역학 보존 확인.

## 10. 리스크·미확인

- **pinocchio IK 수렴/분기선택** — mplib 대비 정확도. → §9 2차로 방어.
- **SAPIEN/ManiSkill osx-arm64 휠·MoltenVK 안정성** — 설치 스모크(§8-1,2)로 조기 확인.
  약한 GPU 렌더 FPS 저하는 공식 주의사항(느리지만 동작).
- **성능** — CPU sim + Mac 렌더라 50에피 배치는 느리다. 인터랙티브/소량엔 충분, 대량 배치는
  여전히 Linux+CUDA 박스가 유리.
- **Option A 로 전환 시** — 제어모드 변경으로 성공률 재검증 필요(§2 단점).
</content>
</invoke>
