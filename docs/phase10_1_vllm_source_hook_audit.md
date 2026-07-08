# Phase 10.1 vLLM Source-Level Hook Audit

## Scope

This audit inspected the installed server environment, not online documentation.

```text
env: contractkv-cu128
vLLM version: 0.10.2
vLLM root: /home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm
artifact: results/hard_systems/vllm_hook_points_v0.json
```

The audit searched for:

```text
scheduler, sequence, sequence_group, block_manager, kv_cache_manager,
prefix_cache, swap_in, swap_out, preemption, block_table,
gpu_blocks, cpu_blocks, request_id, physical_block, logical_block
```

## Summary

The audit found enough source-level evidence to open Phase 10.3 for a guarded runtime probe, but not enough to directly write a real swap implementation without instrumentation.

```text
phase10_3_gate = open_for_probe_only
feasibility = direct_swap_path_present_needs_runtime_validation
```

## Answers To Required Questions

### 1. How does request_id map to vLLM sequence/group?

Status:

```text
likely_available
```

Evidence:

```text
sequence.py
engine/llm_engine.py
core/scheduler.py
core/block_manager.py
engine/async_llm_engine.py
```

Key source evidence includes `Sequence` carrying `request_id`, `llm_engine.py` creating sequence groups, and scheduler/block-manager code consuming those sequence groups.

Conclusion:

`request_id -> sequence/group` is likely recoverable through the existing engine/scheduler path, but the exact live object reference must be confirmed with runtime instrumentation.

### 2. Can prompt token span map to block index?

Status:

```text
likely_available
```

Evidence:

```text
core/block_manager.py
sequence.py
v1/core/kv_cache_utils.py
v1/core/sched/scheduler.py
```

`sequence.py` and attention kernels expose block table concepts, while `core/block_manager.py` owns sequence block tables. A segment token span can already be approximated by:

```text
logical_block_start = token_start // block_size
logical_block_end = ceil(token_end / block_size)
```

Conclusion:

Token-span to logical-block mapping is feasible. Exact mapping requires reading the live block size and live block table.

### 3. Can block index map to physical block id?

Status:

```text
possibly_available
```

Evidence:

```text
core/block_manager.py
attention/ops/triton_unified_attention.py
attention/ops/chunked_prefill_paged_decode.py
sequence.py
```

The audit found `block_tables` and `physical_block_idx` references. `core/block_manager.py` references `physical_block_ids`.

Conclusion:

The source contains physical block id concepts, but direct request-level access to the active physical ids needs a runtime probe.

### 4. Does this vLLM version expose swap_in / swap_out paths?

Status:

```text
symbols_present
```

Evidence:

```text
core/scheduler.py
engine/llm_engine.py
engine/async_llm_engine.py
worker/worker.py
sequence.py
```

The audit found `blocks_to_swap_in` and `blocks_to_swap_out` in scheduler outputs and engine execution paths.

Conclusion:

Swap symbols exist. This is not yet proof that external manual request-level swap is safe. The next step should be a read-only runtime probe that logs scheduler outputs and block counts before attempting active swap.

### 5. If swap is possible, which files are likely modification points?

Candidate files:

```text
engine/llm_engine.py
engine/async_llm_engine.py
core/scheduler.py
core/block_manager.py
worker/worker.py
sequence.py
```

Lower-level attention files expose physical block usage, but they are not the first modification target.

### 6. If direct reuse is not safe, what is the smallest implementation path?

Minimum path:

```text
1. Add read-only instrumentation in scheduler/block-manager.
2. Log request_id, seq_id, logical block table, physical_block_ids.
3. Log scheduler blocks_to_swap_in / blocks_to_swap_out.
4. Confirm sequence/group-level swap can be triggered by existing preemption/swap path.
5. Only then add a guarded request-level hook for sequence/group-level swap.
```

Do not start with segment-level swap. First prove sequence/group-level swap out and swap in.

## Gate For Phase 10.3

Phase 10.3 may proceed only as:

```text
runtime probe first
sequence/group-level before segment-level
read-only counters before active mutation
```

It should not directly implement ContractKV segment-level KV placement yet.

## Fallback If Runtime Probe Fails

If vLLM 0.10.2 cannot safely expose or control block movement, switch to:

```text
Segment-aware prefix cache real metric
```

That fallback must still use real vLLM metrics:

```text
TTFT
p95 TTFT
prefix-cache reuse/hit if observable
SLO-compliant req/s
real model output score
```
