# Phase 1 Qwen3-4B Smoke Report

## Exit Criteria

- vLLM server starts on port `8000`.
- `zh_basic`, `long_summary`, and `json_output` prompts all return.
- No API timeout and no CUDA OOM.
- TTFT, TPOT, output token count, and peak GPU memory are recorded.

## Evidence Files

- `configs/smoke_prompts.jsonl`
- `results/baselines/qwen3_4b_smoke.jsonl`
- `results/baselines/model_feasibility.csv`
- `logs/phase1/qwen3_4b_8192.log`
- `results/manifests/phase1_qwen3_4b_smoke.yaml`

