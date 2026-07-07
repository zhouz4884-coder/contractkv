#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${ENV_NAME:-contractkv-cu128}"
PYTHON_VERSION="${PYTHON_VERSION:-3.10}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
VLLM_VERSION="${VLLM_VERSION:-0.10.2}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}"

if [[ ! -f "$CONDA_SH" ]]; then
  echo "Conda activation script not found: $CONDA_SH" >&2
  exit 11
fi

# shellcheck source=/dev/null
source "$CONDA_SH"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda create -n "$ENV_NAME" "python=${PYTHON_VERSION}" -y
fi

conda activate "$ENV_NAME"
python -m pip install --upgrade pip
python -m pip install "vllm==${VLLM_VERSION}" --extra-index-url "$TORCH_INDEX_URL"

python - <<'PY'
import importlib.metadata as metadata
import torch

print("python_env_ok")
print("torch", torch.__version__)
print("torch_cuda", torch.version.cuda)
print("cuda_available", torch.cuda.is_available())
print("cuda_device_count", torch.cuda.device_count())
print("vllm", metadata.version("vllm"))
PY

