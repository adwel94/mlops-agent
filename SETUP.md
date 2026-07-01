# 환경 세팅 (부트스트랩)

pip 패키지·버전은 [`requirements.txt`](requirements.txt) 가 단일 출처다. 여기엔 매니페스트로
담을 수 없는 **절차적 부트스트랩** — conda env 생성 · WSL 프로비저닝 · 시크릿 — 만 적는다.

설치·검증은 스킬이 대신 해준다: `python scripts/check_maniskill_env.py --fix` 가 requirements.txt
를 읽어 설치하고, 자기가 못 하는 부분(아래 절차)은 이 문서를 가리켜 제안한다.

## Windows (기본 파이프라인)

시뮬·렌더 모두 CPU 백엔드. **env 생성만 수동**이고 패키지는 requirements 가 채운다.

```cmd
conda create -n maniskill python=3.10 -y
conda activate maniskill
pip install -r requirements.txt
python scripts\check_maniskill_env.py       :: 정상 동작 확인
```

## WSL (`task_to_h5` · `ee_verify` · `gr00t_eval`)

이 세 스킬은 모션플래닝/IK 솔버 `mplib`(Linux 전용 바이너리)을 써서 WSL 안에서 돌고 Windows
가 구동한다 (나머지 스킬은 전부 Windows). 시스템 준비(distro·conda·apt)는 여기서 수동으로 한다:

```bash
# 1) Miniconda + maniskill env (Python 3.10)
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh
bash ~/miniconda.sh -b -p ~/miniconda3
~/miniconda3/bin/conda create -n maniskill python=3.10 -y

# 2) 소프트웨어 Vulkan (GPU 없는 WSL에서 sapien 이 씬을 띄우려면 필요)
sudo apt-get update && sudo apt-get install -y mesa-vulkan-drivers

# 3) 패키지 — requirements.txt (mplib·pyzmq·msgpack 은 Linux 마커로 자동 포함)
cd /mnt/c/Users/hun41/PycharmProjects/maniskill
~/miniconda3/envs/maniskill/bin/pip install -r requirements.txt
```

- env 값(배포판·Python 경로·Vulkan ICD)은 `task_to_h5.py` 상단 상수
  (`WSL_DISTRO` / `WSL_PYTHON` / `WSL_VK_ICD`)가 가리킨다. 환경이 다르면 그 상수만 맞추면 된다.
- 소프트웨어 Vulkan은 lavapipe ICD `/usr/share/vulkan/icd.d/lvp_icd.x86_64.json` 를 쓴다.

## 클라우드 (⑤ RunPod, 선택)

파인튜닝·서빙·평가는 외부 GPU(RunPod)에서 돈다. 프로젝트 루트 `.env` 에
`RUNPOD_API_KEY` · `HF_TOKEN` (선택 `WANDB_API_KEY`)을 채우면 클라우드 스킬이 자동 로드한다
(`.env.example` 복사). 이미지 빌드/푸시 등 파드 인프라 세부는 `cloud/runpod/README.md` 참고.
