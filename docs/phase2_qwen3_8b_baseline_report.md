# Phase 2 Qwen3-8B Baseline Report

## Exit Criteria

- `8192` context length succeeds before trying larger contexts.
- `16384` is attempted only after `8192` is recorded.
- `32768` is attempted only after `16384` is recorded; OOM is recorded as memory-pressure motivation.
- Every context length writes a machine-readable row with `error_type`, `log_path`, manifest path, and commit hash.

## Evidence Files

- `results/baselines/model_feasibility.csv`
- `results/baselines/qwen3_8b_context_scaling.csv`
- `logs/phase2/qwen3_8b_8192.log`
- `logs/phase2/qwen3_8b_16384.log`
- `logs/phase2/qwen3_8b_32768.log`
- `results/manifests/phase2_qwen3_8b_*.yaml`

