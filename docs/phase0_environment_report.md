# Phase 0 Environment Report

## Blocker Table

| Blocker | Current Status | Decision Criterion | Evidence After Resolution |
| --- | --- | --- | --- |
| PyTorch CUDA unavailable | blocking | `torch.cuda.is_available() == True` | `results/env/torch_env.json` |
| vLLM unavailable | pending | `python -m vllm.entrypoints.openai.api_server --help` exits normally | `results/env/vllm_help.txt` |
| Model incomplete | pending | tokenizer + config + safetensors + index exist | `results/env/model_integrity.csv` |
| System disk too full | risk | large files stay off `/` | `results/env/df_h.txt` |

## Current Known Facts

- Server: `user@10.15.0.47`
- GPUs: 2 x NVIDIA GeForce RTX 3090, 24 GiB each.
- Driver/CUDA from `nvidia-smi`: driver `570.133.07`, CUDA `12.8`.
- Existing `contractkv` environment has `torch 2.11.0+cu130`; CUDA is not available from PyTorch there.
- Repair strategy: create `contractkv-cu128`; do not mutate the old `contractkv` environment.
- Environment location: `/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/envs/contractkv-cu128`, so CUDA/vLLM packages do not fill the system disk.
- Phase 0-2 model matrix: `Qwen3-4B`, `Qwen3-8B`, `Llama-3.1-8B-Instruct`.
- `Qwen3-14B` is allowed to remain incomplete until its download finishes.
- `Qwen3-Coder-30B-A3B-Instruct` is removed from the current matrix.

## Phase 0 Exit Criteria

- `torch.cuda.is_available() == True`.
- `torch.cuda.device_count() == 2`.
- Both devices are reported as RTX 3090.
- vLLM API server help exits normally.
- `Qwen3-4B`, `Qwen3-8B`, and `Llama-3.1-8B-Instruct` pass model integrity checks.
