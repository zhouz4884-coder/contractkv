# Phase 10.4B Recompute Actuator Probe Report

## Goal

Prove that ContractKV can trigger a real vLLM V1 scheduler/block-pool action:

```text
sequence/group-level release -> recompute later -> request completes
```

This is not HTTP proxy behavior and not dummy tensor copy. It modifies the vLLM V1 scheduler path under an explicit environment-variable guard.

## Implementation

Patch installer:

```text
scripts/install_vllm_v1_recompute_probe.py
```

Summary builder:

```text
scripts/build_recompute_actuator_probe_summary.py
```

The patch is inactive by default. It only runs when:

```text
CONTRACTKV_RECOMPUTE_PROBE=1
```

Runtime event log:

```text
results/hard_systems/vllm_recompute_actuator_events_v0.jsonl
results/hard_systems/vllm_recompute_actuator_events_qwen3_8b_v0.jsonl
```

Summary:

```text
results/hard_systems/vllm_recompute_actuator_probe_v0.csv
```

## Mechanism

The guarded actuator reuses the native vLLM V1 preemption/recompute primitive:

```text
remove request from scheduler.running
kv_cache_manager.free(request)
encoder_cache_manager.free(request)
request.status = PREEMPTED
request.num_computed_tokens = 0
waiting.prepend_request(request)
continue normal scheduling
```

The probe fires once per server process after a running request has at least one computed token.

## Results

| Model | Forced Events | Request Completed | Free GPU Blocks Delta | Preempt Latency ms | Request Latency ms | Success |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| Qwen3-4B | 1 | true | 128 | 0.096080 | 1521.809399 | true |
| Qwen3-8B | 1 | true | 128 | 0.091070 | 1534.503015 | true |

Both debug and primary models completed their requests after forced preemption/recompute.

## Success Criteria

1. Active preemption/recompute was triggered by ContractKV guard: passed.
2. Real vLLM GPU KV block counters changed: passed.
3. Requests recovered and completed: passed.
4. Probe was not HTTP-only proxy behavior: passed.
5. Probe was not dummy tensor copy: passed.

## Interpretation

ContractKV now has a real vLLM V1 actuator:

```text
sequence/group-level recompute/residency control
```

The primitive is not segment-level yet, but it changes the real vLLM GPU KV block pool and allows the request to continue through vLLM scheduling.

## Boundary

This is not active swap and not segment-level block selection. It proves the sequence/group-level recompute actuator. Phase 10.5 should map segment risk to this actuator and evaluate when releasing/recomputing low-risk request state improves admission or SLO behavior without quality collapse.
