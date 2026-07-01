---
name: hf_push_dataset
description: LeRobot 데이터셋 디렉토리(h5_to_lerobot 출력)를 HuggingFace Hub 로 업로드하고, 올라간 결과를 다시 조회해 구조·카운트를 검증한다. scripts/hf_push_dataset.py 래퍼. ④ GR00T 클라우드 흐름에서 로컬 데이터셋과 학습 파드 사이의 다리 — 파드는 부팅 때 이 HF repo 를 받아간다(직접 전송 없이 HF 가 단일 출처). --version vN 으로 불변 버전 태그를 박고 MANIFEST.yaml 에 기록(중복이면 에러 — 버전 불변). --verify-only 로 업로드 없이 기존 repo 점검만도 가능. HF_TOKEN(write) 필요. 인자: <lerobot 디렉토리> <repo_id> [--version vN] [--private] [--verify-only].
---

# hf_push_dataset — LeRobot 데이터셋 HF 업로드 + 검증

`scripts/hf_push_dataset.py` 래퍼. `h5_to_lerobot` 출력(`data/datasets/<task>/lerobot/`)을
HuggingFace dataset repo 로 올리고, **올라간 결과를 다시 조회해 구조·카운트가 맞는지 확인**한다.
④ GR00T 클라우드 흐름에서 **로컬 생성물과 학습 파드 사이의 다리** — 학습 파드는 부팅 때
`fetch_dataset.sh` 로 이 repo 를 받아간다(직접 전송 없이 **HF 가 단일 출처**, 데이터셋이 커져도 확장).

## 전제조건

- `.env` 의 `HF_TOKEN` (write 권한). public repo 면 pull(파드 수신)엔 토큰 불필요 — 무료 사용량 넉넉.
- 업로드 대상은 `h5_to_lerobot` 가 만든 LeRobot v2.1 디렉토리(`meta/ data/ videos/`).

## 호출됐을 때

1. `args` 파싱:
   - 1번째 토큰 = LeRobot 디렉토리 (예: `data/datasets/ThreeColoredCubes-v1/lerobot`). **필수.** `--verify-only` 면 `-` 로 대체 가능.
   - 2번째 토큰 = HF repo id (예: `adwel94/maniskill-threecubes-lerobot`). **필수.**
   - 옵션 `--version vN` (불변 버전 태그 + MANIFEST.yaml 기록), `--task <slug>` (MANIFEST 키 오버라이드), `--private` (기본: public), `--verify-only` (업로드 없이 점검만), `--message "..."`
2. 프로젝트 루트에서 실행:
   ```
   C:\Users\hun41\miniconda3\envs\maniskill\python.exe scripts\hf_push_dataset.py "<DIR>" "<repo_id>"
   ```
3. 업로드 → 검증 결과 보고: repo URL + 4개 체크 결과(아래) + PASS/FAIL.

## 검증 항목 (업로드 직후 자동 / `--verify-only` 단독)

HF repo 를 `list_repo_files` 로 조회하고 `meta/info.json`·`meta/tasks.jsonl` 을 받아 대조:

- 필수 meta 파일 완비 — `info.json, episodes.jsonl, tasks.jsonl, modality.json, stats.json`
- parquet 수 == `info.total_episodes`
- mp4 수 == `info.total_videos`
- tasks.jsonl 행 수 == `info.total_tasks`

하나라도 어긋나면 `RuntimeError` 로 실패(파드가 깨진 데이터셋을 받아 학습하다 과금되는 걸 사전 차단).

## 동작 / 주의사항

- `create_repo(exist_ok=True)` + `upload_folder` — 같은 repo 재실행 시 변경분만 커밋(멱등).
- **task-무관** — repo 내용만 보고 검증. task 이름을 모름.
- 검증은 `h5_to_lerobot` 의 로컬 산출과 별개로 **HF 에 실제 올라간 것**을 본다 — 전송 누락/중단 감지용.
- `--verify-only` 는 업로드 권한이 없어도(public pull) 동작 — 파드 띄우기 전 "데이터 준비됐나" 확인용.

## 예시

| 사용자 입력 | 결과 |
|---|---|
| `/hf_push_dataset data/datasets/ThreeColoredCubes-v1/lerobot adwel94/maniskill-threecubes-lerobot --version v1` | 업로드 + 검증 + `v1` 불변 태그 + MANIFEST 기록 |
| `/hf_push_dataset - adwel94/maniskill-threecubes-lerobot --verify-only` | 업로드 없이 기존 repo 점검 |
| `/hf_push_dataset <DIR> <repo_id> --private` | private repo 로 업로드 |

## HF 명명·버전 정책 (단일 출처)

반복 재학습/재생성이 repo 를 증식(`-ft2`,`-final`)시키거나 덮어쓰기로 과거를 지우는 걸
막는다: **태스크당 repo 하나 + git 태그로 버전** (HF=git 이라 스냅샷이 공짜).

```
데이터셋  adwel94/maniskill-<slug>-lerobot   tag v1, v2 ...                       (생성방식 바뀌면 새 태그·불변)
모델      adwel94/gr00t-<slug>               main + tag <ds_ver>-s<steps>[-full]  (예: v1-s3000)
```

- **HF 태그가 버전 진실, 로컬은 작업 사본** — `data/` 는 gitignore+재생성 가능 → 로컬엔
  최신 빌드 하나만. 모델은 로컬에 없음(파드→HF 직행).
- **버전 단일 출처 = `MANIFEST.yaml`**(커밋됨) — 어떤 버전이 어디 있고 eval 이 얼마인지 잇는 지도.
- **태그는 불변** — `--version v1` 중복이면 **에러**(덮어쓰지 않음; 바뀌었으면 새 번호).
  모델 태그 충돌은 경고만(main 갱신).
- **자동 기록** — `hf_push_dataset --version`→`add_dataset`, `launch_train`→`add_model`(eval=null).
  모델 eval 은 평가 후 수동 `python scripts/manifest.py set-eval <slug> <model> <값>`.
- **slug** = `maniskill-<slug>-lerobot` 에서 추출 → push/train 이 같은 dataset repo 를 알아 MANIFEST 키 일치.
- **학습 이미지는 코드를 담지 데이터를 담지 않는다** — 파드 코드를 빌드 시 굽는다(한 이미지가
  1캠·멀티캠 데이터셋 다 학습). **코드가 바뀔 때만** 재빌드. 태그 `:latest`(launch_train 기본)
  + `:git-<sha>`(불변 추적), `add_model` 이 MANIFEST 모델 항목 `image` 필드에 기록.

학습은 `--hf-dataset-repo <repo>@v1` 로 받아 모델 태그 `v1-s<steps>` 를 자동 도출.

흐름: `/h5_to_lerobot`(포장) → **`/hf_push_dataset --version vN`(업로드+검증+태그)** → `python cloud/train/launch_train.py --hf-dataset-repo <repo>@vN`(학습 파드 — 부팅 때 이 repo 수신).
