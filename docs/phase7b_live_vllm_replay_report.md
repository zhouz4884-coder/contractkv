# Phase 7B Live vLLM Replay Report

## Goal

Run a multi-request workload replay against a real Qwen3-8B vLLM OpenAI-compatible endpoint while applying ContractKV policy decisions and transfer-stall proxy accounting.

Policies:

- No-Contract
- ContractKV-Indep
- ContractKV-Joint

Outputs:

- `results/workload/live_replay_raw_v0.csv`
- `results/workload/live_replay_summary_v0.csv`

## Result

The run completed 420 streaming requests:

| Policy | Raw records |
| --- | ---: |
| No-Contract | 140 |
| ContractKV-Indep | 140 |
| ContractKV-Joint | 140 |

All 420 records have `error_type=none`. The server was stopped after replay, with no vLLM process or GPU memory residue.

## Summary

Aggregate over all datasets:

| Policy | Admission | SLO violation | Quality violation | Mean residual stall ms | Mean TTFT ms | Mean controller overhead ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No-Contract | 1.000 | 0.714 | 0.000 | 0.000 | 221.963 | 0.000 |
| ContractKV-Indep | 0.000 | 0.957 | 1.000 | 40.666 | 261.375 | 0.273 |
| ContractKV-Joint | 1.000 | 0.821 | 0.000 | 12.228 | 233.550 | 0.797 |

Dataset-level rows are in `live_replay_summary_v0.csv`.

## Findings

ContractKV-Joint preserves the quality budget across the live replay, while ContractKV-Indep violates it for every request because it applies the aggressive independent plan. Slack-window copy proxy reduces residual stall relative to critical-path copy.

The 200 ms TTFT SLO is intentionally tight for this setup, so all serving policies experience SLO pressure. Phase 7 should therefore be read as a stress replay, not a claim that the current prototype improves real vLLM throughput.

## Boundary

The vLLM API path is real and streaming. KV placement and copy behavior remain proxy-mode; the live prompt is compacted to keep 420 requests tractable.
