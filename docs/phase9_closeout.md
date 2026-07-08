# Phase 9 Closeout

## What Phase 9 Completed

Phase 9 moved ContractKV from an external proxy-only workflow into a vLLM-adjacent request lifecycle record:

```text
trace -> request metadata -> read-only observer -> request-adjacent prefetch orchestrator -> replay join
```

Completed artifacts:

```text
scripts/vllm_metadata_hook_proxy.py
scripts/vllm_observer_stats.py
scripts/vllm_prefetch_orchestrator_proxy.py
scripts/run_phase9_metadata_observer_replay.py

results/runtime/vllm_metadata_hook_logs_v0.jsonl
results/runtime/vllm_observer_stats_v0.csv
results/runtime/vllm_prefetch_orchestrator_proxy_v0.csv
results/runtime/phase9_metadata_observer_replay_v0.csv
results/runtime/phase9_metadata_observer_replay_summary_v0.csv

docs/phase9a_vllm_metadata_hook_report.md
docs/phase9b_vllm_block_stats_observer_report.md
docs/phase9c_prefetch_orchestrator_report.md
docs/phase9d_metadata_observer_replay_report.md
```

## Main Evidence

The replay produced 420 rows:

```text
140 traces x 3 policies
```

Metadata and observer joining are stable:

```text
metadata_success_rate = 1.0
observer_join_success_rate = 1.0
```

ContractKV-Joint remains quality-safe under the existing proxy risk ledger:

```text
ContractKV-Joint quality_violation_rate = 0.0
ContractKV-Indep quality_violation_rate = 1.0
```

Request-adjacent transfer orchestration reduces residual stall:

```text
ContractKV-Indep mean residual stall = 60.062 ms
ContractKV-Joint mean residual stall = 20.916 ms
```

## What This Proves

1. ContractKV segment metadata, token counts, risk budget, SLO budget, tool slack, and decision plans can be attached to request ids.
2. Read-only request observer rows can be joined back to ContractKV metadata without changing the OpenAI response format.
3. A request-adjacent prefetch/offload proxy can use slack and predicted transfer size to choose copy strategy.
4. Joint policy keeps the same quality-budget boundary observed in Phase 7/8 while adding metadata and observer plumbing.

## What This Still Does Not Prove

Phase 9 still does not claim:

```text
real vLLM KV block movement
true KV cache memory saving
real block table control
real INT2/K8V4 KV quantization
production serving throughput improvement
```

The observer explicitly marks block-level stats as unavailable rather than fabricating them.

## Decision For Next Phase

The next hard-system step should be a source-level vLLM hook audit:

```text
request_id -> sequence/group -> token span -> block table -> swap_in/swap_out feasibility
```

Only after that audit should ContractKV attempt real vLLM KV block movement.
