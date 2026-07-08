# Phase 10.4 vLLM V1 Actuator Audit

## Goal

Phase 10.4 answers one question:

```text
What real vLLM V1 object can ContractKV control?
```

This phase moves beyond observer/proxy replay and audits actual vLLM V1 actuator candidates.

## Artifact

```text
results/hard_systems/vllm_v1_actuator_candidates.json
```

Audit script:

```text
scripts/audit_vllm_v1_actuators.py
```

Audited environment:

```text
vLLM version: 0.10.2
vLLM root: /home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm
```

The audit ignores lines inside ContractKV probe functions so the result is not contaminated by Phase 10.3 instrumentation.

## Focus Files

```text
v1/core/sched/scheduler.py
v1/core/kv_cache_manager.py
v1/core/block_pool.py
v1/worker/gpu_model_runner.py
engine/async_llm_engine.py
worker/worker.py
```

## Actuator Decisions

| Actuator | Decision | Can Observe | Can Trigger | Risk | 10.4B Status |
| --- | --- | --- | --- | --- | --- |
| active_swap | blocked | false | blocked | high | do not probe next |
| preemption_recompute | open | true | unknown before probe | medium | probe next |
| prefix_cache_layout | open | true | yes | low | fallback route |
| admission_gate | open | true | yes | low | auxiliary only |

Recommended 10.4B probe:

```text
preemption_recompute
```

## Source Evidence

### Active Swap

Legacy engine/worker paths still contain `blocks_to_swap_in` and `blocks_to_swap_out` handling:

```text
engine/async_llm_engine.py
worker/worker.py
```

However, Phase 10.3B observed zero natural swap events, and this audit did not find a clean V1 scheduler-to-worker active swap control path. Therefore:

```text
active_swap = blocked
```

### Preemption / Recompute

V1 scheduler has a native preemption branch when `kv_cache_manager.allocate_slots(...)` returns `None`. The branch:

```text
removes a request from running
frees request KV blocks through kv_cache_manager.free(...)
marks the request PREEMPTED
sets num_computed_tokens = 0
prepends the request back to waiting
lets it recompute later
```

Relevant files:

```text
v1/core/sched/scheduler.py
v1/core/kv_cache_manager.py
v1/core/block_pool.py
```

This is a real vLLM V1 scheduler/block-pool primitive, so it is the strongest immediate actuator.

### Prefix Cache Layout

Prefix-cache paths are visible in:

```text
v1/core/sched/scheduler.py
v1/core/kv_cache_manager.py
v1/core/block_pool.py
v1/worker/gpu_model_runner.py
```

This route remains open as the safest fallback if recompute/residency control becomes too invasive.

### Admission Gate

Admission/defer is easy to implement outside or adjacent to vLLM, but it is a weaker system contribution unless paired with real block or prefix-cache behavior.

## Decision

Proceed to Phase 10.4B with:

```text
sequence/group-level preemption_recompute actuator probe
```

Do not pursue active swap as the next probe.

## Updated Research Position

ContractKV should now be framed as:

```text
a segment-aware recompute/residency controller for vLLM V1
```

not as a swap-only KV offloader.

If recompute control scales, it becomes the hard-system route. If it does not, the fallback is real prefix-cache canonical segment layout.
