# Phase 10.3A vLLM Runtime Probe Report

## Goal

Add read-only instrumentation inside vLLM and verify whether real requests expose:

```text
request_id -> sequence/group -> logical block table -> physical block ids
```

The probe must not change scheduling, KV allocation, model outputs, or OpenAI response format.

## Instrumentation

Installed guarded probe scripts:

```text
scripts/install_vllm_runtime_probe.py
scripts/install_vllm_v1_runtime_probe.py
scripts/summarize_vllm_runtime_probe.py
```

The active server path is vLLM V1:

```text
/home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm/v1/core/sched/scheduler.py
```

The legacy `llm_engine.py` probe was installed but did not fire because the OpenAI server initialized a V1 engine.

Probe control:

```text
CONTRACTKV_PROBE=1
CONTRACTKV_PROBE_LOG=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/hard_systems/vllm_runtime_probe_events_v0.jsonl
```

When `CONTRACTKV_PROBE` is unset, the instrumentation is inactive.

## Outputs

```text
results/hard_systems/vllm_runtime_probe_events_v0.jsonl
results/hard_systems/vllm_runtime_probe_summary_v0.csv
```

Smoke responses were also saved:

```text
results/hard_systems/qwen3_4b_probe_smoke_response.json
results/hard_systems/qwen3_8b_probe_smoke_response.json
```

## Smoke Results

| Model | Request Events | Scheduler Events | Prompt Tokens | Block Size | Logical Blocks | Physical Block IDs | Join Success | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Qwen3-4B | 32 | 32 | 19 | 16 | 4 | 4 | true | open |
| Qwen3-8B | 32 | 32 | 19 | 16 | 4 | 4 | true | open |

The summary file also contains an `unknown` scheduler-only row. This row has no scheduled request attached and is ignored for request-level joins.

## Required Checks

1. `request_id -> seq/group` is observable through V1 scheduler request ids.
2. `block_size` is observable and was `16`.
3. Logical block table length is observable.
4. Physical block ids are readable through `kv_cache_manager.get_block_ids(request_id)`.
5. Free/used GPU block counters are readable through the V1 block pool.
6. `blocks_to_swap_in` and `blocks_to_swap_out` fields are present in scheduler output records.
7. Qwen3-4B and Qwen3-8B smoke requests both returned normal OpenAI-compatible responses.

## Gate Decision

```text
phase10_3b_gate = open
phase10_3c_gate = closed_until_natural_path_is_understood
```

Phase 10.3A succeeds as a read-only runtime probe. It opens Phase 10.3B natural swap/preemption observation, but it does not by itself authorize active swap code.

## Boundary

This phase did not move real KV blocks. It only proved that V1 request/block observability is available under a guarded probe.
