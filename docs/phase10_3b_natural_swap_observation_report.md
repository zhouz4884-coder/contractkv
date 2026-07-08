# Phase 10.3B Natural Swap Observation Report

## Goal

Create KV pressure and observe whether vLLM 0.10.2 naturally emits:

```text
blocks_to_swap_out
blocks_to_swap_in
preempted sequence groups
GPU/CPU block counter changes
```

No active swap calls were added in this phase.

## Inputs

Instrumentation from Phase 10.3A remained enabled:

```text
CONTRACTKV_PROBE=1
```

Runner:

```text
scripts/send_concurrent_probe_requests.py
scripts/build_natural_swap_observation.py
```

Outputs:

```text
results/hard_systems/vllm_natural_swap_events_v0.jsonl
results/hard_systems/vllm_natural_swap_observation_v0.csv
```

Request outcome records:

```text
results/hard_systems/qwen3_4b_natural_swap_requests.jsonl
results/hard_systems/qwen3_8b_natural_swap_requests.jsonl
```

## Server Configurations

| Model | max_model_len | max_num_seqs | gpu_memory_utilization | Concurrent Requests | Context Words |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3-4B | 8192 | 8 | 0.45 | 6 | 7000 |
| Qwen3-8B | 8192 | 2 | 0.88 | 3 | 6000 |

An initial Qwen3-8B attempt with `gpu_memory_utilization=0.65` failed at startup:

```text
Available KV cache memory: -0.18 GiB
ValueError: No available memory for the cache blocks.
```

This was recorded as an invalid pressure configuration, then retried with `gpu_memory_utilization=0.88`.

## Results

| Model | Events | Requests Observed | Swap Events | Preemptions | Min Free GPU Blocks | Max Used GPU Blocks | Observed Behavior |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Qwen3-4B | 188 | 12 | 0 | 4 | 6 | 1299 | preemption_or_recompute_without_swap |
| Qwen3-8B | 94 | 6 | 0 | 0 | 1535 | 851 | no_swap_or_preemption_observed |

Qwen3-4B completed 12 pressure requests. Qwen3-8B completed 6 pressure requests after the valid restart.

## Interpretation

The current vLLM V1 path did not naturally populate scheduler swap arrays under these pressure runs.

For Qwen3-4B, pressure reached a near-empty GPU block pool and vLLM emitted preemption/recompute-like behavior, but still no `blocks_to_swap_in` or `blocks_to_swap_out` events.

For Qwen3-8B, the safer valid configuration completed all requests without natural swap or preemption.

## Phase 10.3C Gate

```text
phase10_3c_active_swap_gate = closed
reason = natural observation does not expose a reusable V1 swap_out/swap_in path
```

The next hard-system step should audit V1 `kv_cache_manager`, `block_pool`, and preemption/recompute code paths for a guarded active sequence/group-level intervention point. It should not blindly call legacy swap paths.

## What This Proves

1. Phase 10.3A observability works under real pressure requests.
2. vLLM V1 exposes request/block counters during scheduling.
3. Natural swap was not observed in this configuration.
4. Natural preemption/recompute was observed for Qwen3-4B under tight GPU block pressure.

## What This Does Not Prove

This phase does not prove active KV swap, segment-level KV movement, or increased admission from real swap. Phase 10.3C remains gated.
