#!/usr/bin/env bash
set -euo pipefail

DISK="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9"
ENV_PREFIX="$DISK/envs/contractkv-sglang"
CONDA_PKGS="$DISK/cache/conda_pkgs"
PIP_CACHE="$DISK/cache/pip"
CONDA="/home/user/miniconda3/bin/conda"

mkdir -p "$CONDA_PKGS" "$PIP_CACHE" "$DISK/envs"
export CONDA_PKGS_DIRS="$CONDA_PKGS"
export PIP_CACHE_DIR="$PIP_CACHE"

if [[ ! -x "$ENV_PREFIX/bin/python" ]]; then
  "$CONDA" create -y -p "$ENV_PREFIX" python=3.11 pip
fi

"$ENV_PREFIX/bin/python" -m pip install --upgrade pip
"$ENV_PREFIX/bin/python" -m pip install "sglang[all]==0.4.9.post6" "protobuf==7.35.1"
"$ENV_PREFIX/bin/python" - <<'PY'
import json
import google.protobuf
import sglang
import torch

print(json.dumps({
    "sglang": getattr(sglang, "__version__", "unknown"),
    "protobuf": google.protobuf.__version__,
    "torch": torch.__version__,
    "torch_cuda": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "gpu_count": torch.cuda.device_count(),
}, indent=2))
PY

echo SGLANG_EXTERNAL_ENV_READY
