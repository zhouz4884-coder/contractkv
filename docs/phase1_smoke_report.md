# Phase 1 Qwen3-4B Smoke Report

## Result

Phase 1 passed on `2026-07-08`.

Server configuration:

- Model: `Qwen3-4B`
- Backend: vLLM OpenAI-compatible API
- Port: `8000`
- GPU: `0`
- Tensor parallel size: `1`
- dtype: `float16`
- `max_model_len`: `8192`
- `max_num_seqs`: `4`
- Startup time: `162` seconds
- Peak GPU memory: `19.814` GiB

Smoke prompt results:

| Prompt | Success | Error Type | TTFT ms | TPOT ms | Output Chunks |
| --- | --- | --- | ---: | ---: | ---: |
| `zh_basic` | true | `none` | 564.067 | 13.067 | 128 |
| `long_summary` | true | `none` | 78.608 | 13.186 | 128 |
| `json_output` | true | `none` | 40.016 | 12.981 | 128 |

Note: the `json_output` prompt verifies API return and stream timing. It does not yet enforce strict JSON-only decoding.

## Exit Criteria

- Passed: vLLM server starts on port `8000`.
- Passed: `zh_basic`, `long_summary`, and `json_output` prompts all return.
- Passed: no API timeout and no CUDA OOM.
- Passed: TTFT, TPOT, output chunk count, and peak GPU memory are recorded.

## Evidence Files

- `configs/smoke_prompts.jsonl`
- `results/baselines/qwen3_4b_smoke.jsonl`
- `results/baselines/model_feasibility.csv`
- `logs/phase1/qwen3_4b_8192.log`
- `results/manifests/phase1_qwen3_4b_smoke.yaml`
