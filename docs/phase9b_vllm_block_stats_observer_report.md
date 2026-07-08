# Phase 9B vLLM Block Stats Observer Report

## Goal

Add a read-only observer that records request-level serving-path statistics and can be joined with ContractKV metadata by `request_id`.

## Method

Script:

```text
scripts/vllm_observer_stats.py
```

Inputs:

```text
results/runtime/vllm_metadata_hook_logs_v0.jsonl
results/workload/live_replay_raw_v0.csv
```

Output:

```text
results/runtime/vllm_observer_stats_v0.csv
```

The observer reuses Phase 7 live replay request timing for:

```text
prompt_tokens
TTFT
TPOT
total latency
```

It also records a deterministic GPU-memory sample proxy from prompt size for request-level joining. Block-level vLLM internals are not exposed through this OpenAI-side observer, so those fields are marked:

```text
block_stats_available = false
block_stats_source = unavailable_vllm_openai_observer
```

## Result

The observer produced:

```text
420 observer rows
100% request_id join coverage against metadata
```

## Boundary

No block-manager or physical KV block statistics are fabricated. True block table observation remains a later vLLM-internal hook task.
