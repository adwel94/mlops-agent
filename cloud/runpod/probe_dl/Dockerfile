# Lightweight dataset-download probe — reproduce/diagnose the RunPod-only
# snapshot_download hang WITHOUT the heavy train image (no CUDA/torch/gr00t,
# no 15GB model pull). Builds in seconds so the download fix can be iterated
# cheaply in the real pod network. Reports results to the Discord STDOUT webhook.
FROM python:3.10-slim
RUN pip install --no-cache-dir "huggingface_hub[hf_transfer]"
COPY probe_dl.py /probe_dl.py
ENTRYPOINT ["python", "-u", "/probe_dl.py"]
