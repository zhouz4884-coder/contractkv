# Phase 9D Metadata + Observer + Orchestrator Replay Report

## Goal

Join Phase 9A metadata, Phase 9B observer rows, and Phase 9C orchestrator proxy rows into a single replay table over the same 140 workload traces and three policies.

## Method

Script:

```text
scripts/run_phase9_metadata_observer_replay.py
```

Inputs:

```text
results/runtime/vllm_metadata_hook_logs_v0.jsonl
results/runtime/vllm_observer_stats_v0.csv
results/runtime/vllm_prefetch_orchestrator_proxy_v0.csv
```

Outputs:

```text
results/runtime/phase9_metadata_observer_replay_v0.csv
results/runtime/phase9_metadata_observer_replay_summary_v0.csv
```

## Result

Replay coverage:

```text
420 request-policy rows
140 workload traces
3 policies
metadata_success_rate = 1.0 for all policies
observer_join_success_rate = 1.0 for all policies
```

Summary:

| Policy | Requests | Metadata success | Observer join | Mean overhead ms | Mean TTFT ms | Mean residual stall ms | Quality violation | SLO violation | Admission |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No-Contract | 140 | 1.0 | 1.0 | 0.003 | 221.963 | 0.000 | 0.0 | 0.714 | 1.0 |
| ContractKV-Indep | 140 | 1.0 | 1.0 | 1.154 | 321.437 | 60.062 | 1.0 | 0.957 | 0.0 |
| ContractKV-Joint | 140 | 1.0 | 1.0 | 0.863 | 254.466 | 20.916 | 0.0 | 0.850 | 1.0 |

## Interpretation

ContractKV-Joint preserves the Phase 7/8 quality-budget behavior while attaching metadata and observer records to request ids. The request-adjacent orchestrator lowers residual stall relative to the Indep critical-path copy policy.

## Boundary

This replay validates metadata propagation, observer joining, and transfer-proxy orchestration. It does not validate real KV placement, real KV block swapping, or production throughput.
