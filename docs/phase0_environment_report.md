# Phase 0 Environment Report

## Blocker Table

| Blocker | Current Status | Decision Criterion | Evidence After Resolution |
| --- | --- | --- | --- |
| PyTorch CUDA unavailable | resolved | `torch.cuda.is_available() == True` | `results/env/torch_env.json` |
| vLLM unavailable | resolved | `python -m vllm.entrypoints.openai.api_server --help` exits normally | `results/env/vllm_help.txt` |
| Model incomplete | resolved | tokenizer + config + safetensors + index exist | `results/env/model_integrity.csv` |
| System disk too full | mitigated | large files stay off `/` | `results/env/df_h.txt` |

## Current Known Facts

- Server: `user@10.15.0.47`
- GPUs: 2 x NVIDIA GeForce RTX 3090, 24 GiB each.
- Active environment: `contractkv-cu128`.
- Python: `3.10.20`.
- PyTorch: `2.8.0+cu128`.
- PyTorch CUDA runtime: `12.8`.
- `torch.cuda.is_available()`: `true`.
- `torch.cuda.device_count()`: `2`.
- vLLM: `0.10.2`; API server help is callable.
- Compatibility fix: `transformers==4.55.2` is pinned for vLLM 0.10.2. The earlier `transformers 5.13.0` caused Qwen tokenizer startup failure.
- System disk cleanup removed stale pip/vLLM caches from `/home/user/.cache`; `/` now has about 27 GiB free and is 88% used.
- Keep datasets, model downloads, caches, logs, and checkpoints on `/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9`.
- `scripts/setup_contractkv_cu128.sh` and `scripts/run_vllm_server.sh` default `TMPDIR`, Hugging Face, torch, triton, and vLLM caches to the 8T disk via `CONTRACTKV_DISK_ROOT`.
- The currently verified manual environment is `/home/user/miniconda3/envs/contractkv-cu128`; it is left in place to avoid disturbing the validated Phase 0-2 run. Future scripted installs default to `${CONTRACTKV_DISK_ROOT}/envs/contractkv-cu128`.
- Phase 0-2 model matrix: `Qwen3-4B`, `Qwen3-8B`, `Llama-3.1-8B-Instruct`.
- `Qwen3-14B` is complete in this run, but remains non-blocking for Phase 0-2.
- `Qwen3-Coder-30B-A3B-Instruct` is removed from the current matrix.

## Phase 0 Exit Criteria

- Passed: `torch.cuda.is_available() == True`.
- Passed: `torch.cuda.device_count() == 2`.
- Passed: both devices are reported as RTX 3090.
- Passed: vLLM API server help exits normally.
- Passed: `Qwen3-4B`, `Qwen3-8B`, and `Llama-3.1-8B-Instruct` pass model integrity checks.
- Passed: `Qwen3-14B` also passes model integrity checks, but is not required for Phase 0-2.
