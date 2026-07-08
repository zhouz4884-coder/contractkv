#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${ENV_NAME:-contractkv-cu128}"
ENV_PREFIX="${ENV_PREFIX:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/envs/contractkv-cu128}"
PYTHON_VERSION="${PYTHON_VERSION:-3.10}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
VLLM_VERSION="${VLLM_VERSION:-0.10.2}"
TMPDIR="${TMPDIR:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/tmp/contractkv-cu128}"
CONDA_PKGS_DIRS="${CONDA_PKGS_DIRS:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/conda-pkgs/contractkv-cu128}"

cleanup() {
  rm -rf "$TMPDIR"
  if [[ "${KEEP_CONDA_PKGS:-0}" != "1" ]]; then
    rm -rf "$CONDA_PKGS_DIRS"
  fi
}
trap cleanup EXIT

if [[ ! -f "$CONDA_SH" ]]; then
  echo "Conda activation script not found: $CONDA_SH" >&2
  exit 11
fi

# shellcheck source=/dev/null
source "$CONDA_SH"

mkdir -p "$TMPDIR" "$CONDA_PKGS_DIRS" "$(dirname "$ENV_PREFIX")"
export TMPDIR CONDA_PKGS_DIRS

if [[ ! -x "$ENV_PREFIX/bin/python" ]]; then
  conda create -p "$ENV_PREFIX" "python=${PYTHON_VERSION}" -y
fi

conda activate "$ENV_PREFIX"

conda install -p "$ENV_PREFIX" -y --override-channels -c defaults \
  "pytorch=2.8=*gpu_cuda128_py310*" \
  "torchvision=0.23=*cuda128py310*" \
  "torchaudio=2.8=*cuda128py310*" \
  "triton=3.4=*cuda128py310*"

python -m pip install --upgrade pip
python -m pip install --no-cache-dir "vllm==${VLLM_VERSION}"

python - <<'PY'
import importlib.metadata as metadata
import torch

print("python_env_ok")
print("torch", torch.__version__)
print("torch_cuda", torch.version.cuda)
print("cuda_available", torch.cuda.is_available())
print("cuda_device_count", torch.cuda.device_count())
print("vllm", metadata.version("vllm"))
if not torch.cuda.is_available():
    raise SystemExit("cuda_unavailable")
if str(torch.version.cuda) != "12.8":
    raise SystemExit(f"unexpected_torch_cuda={torch.version.cuda}")
PY
