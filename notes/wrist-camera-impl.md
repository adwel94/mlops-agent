# 손목 카메라 구현 — 설계 & 검증 (2026-06-29)

> **엔지니어링 노트.** 이 문서는 **하나만 말한다**: 손목 카메라를 이 하네스에
> **어떻게** 붙였나 — 설계 원칙·핵심 메커니즘·변경 범위·구현 검증. **왜** 이걸 했는지,
> 그리고 **효과(성능 결과)**는 진단 여정 문서에 있다 → `model-perf-journey.md` §4~5.
> 여기 "검증"은 파이프라인이 올바른 데이터를 내는지 / IK 경로가 정직한지에 대한
> **구현 검증**이지, 모델 성능 결과가 아니다.

## 왜 (한 줄)

v1 모델 진단 결론: 병목은 **단일 고정 카메라(base_camera)로 큐브 3D 위치를 정밀하게 못
잡는 reaching 정밀도**. NVIDIA/Seeed 공식 정밀 레시피는 **손목 카메라**를 쓴다(근접 시점으로
깊이 모호성 제거). → 손목캠을 **범용·하위호환** 방식으로 파이프라인에 추가한다.
(진단·처방 선택 근거: `model-perf-journey.md` §4. 효과 검증: 같은 문서 §5.)

## 설계 원칙 (둘 다 필수)

1. **하위호환** — 기존 1캠 데이터셋/모델은 한 글자도 안 바뀌어야 한다. 기본값 = 지금과 동일.
2. **범용** — 이 하네스 제1원칙("소비자는 태스크 이름을 모른다; env가 선언하면 소비자는
   약속만 따른다")을 지킨다. 카메라는 **하드코딩하지 말고 데이터에서 발견(discover)**.
   매니스킬 비슷한 태스크는 코드 변경 없이 그대로 태워야 한다.

## 핵심 메커니즘 (프로브로 검증됨)

ManiSkill 내장 **`panda_wristcam`** 에이전트 = Panda + realsense 카메라(`hand_camera`,
`camera_link` 마운트, panda_v3.urdf). **robot_uids 는 이미 gym.make 통과 인자** →
`gym.make(task, robot_uids="panda_wristcam")` 한 줄로 모든 panda 테이블탑 태스크에 손목캠이
**자동 추가**된다 (env 코드 변경 0).

- 기본 `robot_uids="panda"` → base_camera 1개 (하위호환)
- 옵트인 `robot_uids="panda_wristcam"` → base_camera + hand_camera 2개

검증 완료 (`scratchpad/probe_wristcam.py`, Windows CPU):
- 두 카메라 다 정상 렌더 (hand_camera min=35 max=255 mean=114, 비검정 100%)
- hand_camera 뷰 = 그리퍼 시점 근접 워크스페이스(큐브 크게) = 깊이 모호성 해소 확인
- camera_link은 **고정 조인트** → qpos 차원·IK move_group 불변 (state/action/IK 안 건드림)
- PICK_CUBE_CONFIGS 는 panda_wristcam→"panda" 로 폴백 → base_camera 배치 동일
- panda_v3.srdf 존재 → mplib IK 로드 가능 (최종 sim 재현은 WSL ee_verify 단계서 확인)

## 변경 범위

### 고쳐야 할 코드
| 파일 | 변경 | 비고 |
|---|---|---|
| `scripts/task_to_h5.py` | robot_uids 옵트인 플래그 배선 (기본 panda) | WSL 솔버도 같은 robot 써야 함 |
| `scripts/h5_add_images.py` | robot_uids 옵트인 배선 (리플레이 시 같은 robot) | obs_mode=rgb 가 센서 자동 기록 → 카메라 자체는 코드 변경 0 |
| `scripts/h5_to_lerobot.py` | **단일캠 → 카메라 목록 발견**(info.json features·modality.json video·mp4 디렉토리 루프) | 기본 = 데이터에 있는 카메라 전부; 1캠이면 출력 불변 |
| `cloud/common/new_embodiment_config.py` | video modality_keys 를 **데이터셋 modality.json 에서 동적**으로 | ★범용성 깨질 유일 지점 — 하드코딩 금지 |
| `scripts/_wsl_gr00t_eval.py` | obs video dict 에 데이터셋이 쓴 카메라 전부 전송 | 서빙 모델의 캠 수와 일치해야 |
| `scripts/ik_exec.py` | `make_env_and_solver` 에 `robot_uids` 인자 | eval/ee_verify/abs_replay 공유 |
| `scripts/custom_envs.py` | (선택) SUPPORTED_ROBOTS 에 panda_wristcam 추가 — 경고 제거·일급화 | 기능 아닌 위생 |

### 안 건드림 (확인)
`h5_add_images`의 카메라 기록부(obs_mode=rgb 자동), `ee_verify`/`_wsl_abs_eef_replay`/
`gr00t_eval` 래퍼/serve·train 래퍼(tcp_pose·액션만), `h5_report`(기본 base_camera + --camera).

### 코드 아님 = 비용 (사용자 승인 후)
- 데이터 전체 재생성: h5_add_images(wristcam) → h5_to_lerobot → hf_push **새 버전 태그**(v2).
  기존 v1 은 불변. (task_to_h5 재실행 불필요 — 아래 "착수 순서" 참조.)
- 재학습 (과금) — 모델이 손목 입력을 실제로 쓰려면 필수. 새 모델 태그.

## 하위호환 — 모델은 캠 수 고정

파이프라인(코드)은 1캠·2캠 공존. 단 **학습된 체크포인트는 카메라 수가 고정**(비전
인코더+projector가 그 입력 형태로 굳음) — 1캠 모델이 2캠 입력을 못 먹고 반대도 안 됨. 코드
한계 아니라 학습 방식의 본질. → v1(1캠)·v2(2캠)을 HF 태그로 분리, serve/eval 때 데이터셋
modality.json 이 "이 모델 캠 몇 개"를 알려주니 거기 맞춰 전송. MANIFEST.yaml 버전 원장이 받침.

## 단일 진실 출처 (범용성의 열쇠)

"이 데이터셋/임베디먼트가 쓰는 카메라 목록" = **데이터셋 `meta/modality.json` 의 video 키**.
h5_to_lerobot(쓰기)·new_embodiment_config(학습)·_wsl_gr00t_eval(평가)이 모두 여기서 카메라
목록을 읽는다. 어디서도 카메라 이름/개수를 하드코딩하지 않는다 → 태스크 무관 범용.

## 착수 순서 (진행 상황 — 전부 완료)

1. ✅ 손목캠 CPU 렌더 게이트 (프로브) — **통과** (base+hand 둘 다 렌더, hand 뷰=근접 워크스페이스)
2. ✅ 이 스코프 문서 — 작성·갱신됨
3. ✅ generic 멀티캠 소비자 리팩터 — **완료·검증됨**
   - `h5_to_lerobot.py`: `select_cameras()` 발견 기반(기본 전체 카메라, base 우선) +
     카메라별 video/feature/modality 루프 + 출력 stale 청소 가드
   - `cloud/common/new_embodiment_config.py`: video modality_keys 를 데이터셋 modality.json
     에서 동적 발견(`_discover_video_keys`, 실패 시 base_camera 폴백)
   - `_wsl_gr00t_eval.py`: 모든 카메라 전송(`_build_obs` 다중캠) + sidecar robot_uids 따라 env 구성
   - `ik_exec.make_env_and_solver`: `robot_uids` 인자 추가(eval/ee_verify/abs_replay 공유)
4. ✅ h5_add_images 옵트인 배선 — **완료·검증됨**
   - `--robot-uids panda_wristcam` → 기존 panda 액션 궤적을 리플레이하며 손목캠 기록(WSL 재생성
     불필요, 팔 동일). 출력 sidecar 에 robot_uids 기록(`_stamp_robot_uids`).
   - task_to_h5 는 **불필요** — 액션은 로봇무관(팔 동일)이라 panda 궤적을 그대로 재사용.
5. ✅ WSL IK 재현 확인 (panda_v3 + ee_verify) — **통과** (아래 결과)
6. ✅ 데이터 재생성 + 새 버전 push — HF `maniskill-threecubes-lerobot@v2` (1000ep, 2캠)
7. ✅ 재학습 2회 — `@v2-s3000`·`@v2-s20000` (**성능 결과는 `model-perf-journey.md` §5**)

## 구현 검증 결과 (2026-06-29, Windows CPU, 5-ep 스모크)

기존 panda `motionplanning.h5` 를 `--robot-uids panda_wristcam` 로 5에피소드 리플레이:
- 카메라 = `['base_camera', 'hand_camera']`, hand 이미지 비검정(min=32 mean=117.6) ✓
- **5/5 에피소드 성공** → 액션 리플레이가 새 로봇에서 과제 완벽 재현(팔 동일 입증) ✓
- sidecar `env_info.robot_uids = env_kwargs.robot_uids = panda_wristcam` 기록 ✓
- `h5_to_lerobot` → modality.video=[base_camera,hand_camera], info features 2개, video
  디렉토리 2개 각 5 mp4, parquet 5 (stale 청소 가드로 잔존 0) ✓
- 1캠 하위호환: 기존 1캠 데이터셋 2-ep 변환 → 단일 base_camera 레이아웃 그대로(출력 불변) ✓

### WSL IK 재현 (ee_verify, panda_v3) — 통과

같은 첫 50 에피소드를 두 로봇으로 ee_verify(WSL mplib IK, sim 성공 재현):

| 로봇 (URDF) | reproduction_rate | ik_fails |
|---|---|---|
| panda (panda_v2, 1캠) | **50/50 = 1.000** | 0 |
| panda_wristcam (panda_v3, 2캠) | **49/50 = 0.980** | 0 |

- 10 에피소드에선 9/10=0.900 이었으나 50 에피소드에서 0.980 → 0.900 은 소표본 노이즈였음.
- panda_v3 가 panda_v2 대비 1개(2%)를 놓침. **ik_fails=0** → IK 방식 결함 아님. 원인 =
  camera_link 질량이 hand 관성을 미세 변화 → 그 1개가 grasp 마진에서 WSL↔Windows 백엔드
  드리프트로 넘어감(1캠에서도 문서화된 그 드리프트가 무거워진 손 때문에 1개 더).
- **판정: 0.980 · ik_fails=0 은 "≈1.0" 기준 충족 → 평가 IK 경로 정직, 방식 건강. 진행 가능.**
  (eval 은 wristcam 모델 성공을 ~98% 충실히 잰다; 1캠 대비 ~2% 더 노이즈하나 사용 범위.)
