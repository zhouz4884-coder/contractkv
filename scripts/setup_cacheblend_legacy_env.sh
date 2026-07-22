#!/usr/bin/env bash
set -euo pipefail

DISK=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
ENV="$DISK/envs/contractkv-cacheblend-041"
BASE_PYTHON="${BASE_PYTHON:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
export PIP_CACHE_DIR="$DISK/cache/pip" TMPDIR="$DISK/tmp"
mkdir -p "$PIP_CACHE_DIR" "$TMPDIR" "$(dirname "$ENV")"

if [[ ! -x "$ENV/bin/python" ]]; then
  "$BASE_PYTHON" -m venv "$ENV"
fi
"$ENV/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 10), sys.version'
"$ENV/bin/python" -m pip install --index-url https://pypi.org/simple -U pip
"$ENV/bin/python" -m pip install --index-url https://download.pytorch.org/whl/cu121 'torch==2.2.1'
"$ENV/bin/python" -m pip install --index-url https://pypi.org/simple --no-build-isolation 'vllm==0.4.1' rouge_score
# vLLM 0.4.1/Torch 2.2 extensions were built against NumPy 1.x.  Pin the
# newest Transformers release that supports Llama 3.1 without requiring a
# newer Torch, instead of accepting today's incompatible resolver choices.
"$ENV/bin/python" -m pip install --index-url https://pypi.org/simple \
  'numpy<2' 'transformers==4.43.3' 'tokenizers<0.20,>=0.19'
"$ENV/bin/python" - <<'PY'
import numpy, torch, transformers, vllm
print({"torch": torch.__version__, "torch_cuda": torch.version.cuda,
       "vllm": vllm.__version__, "numpy": numpy.__version__,
       "transformers": transformers.__version__,
       "cuda_available": torch.cuda.is_available()})
PY
echo CACHEBLEND_ENV_READY
