# Phase 13D-B Process-Isolated RAR A/B Calibration

## Frozen configuration

Two fresh Qwen3-8B servers were launched sequentially with identical settings:

```text
gpu_memory_utilization = 0.78
max_model_len = 8192
max_num_seqs = 8
prefix caching = enabled
12 unique long requests
client concurrency = 12
max_tokens = 256
```

The default run set `CONTRACTKV_ANCHOR_RECOMPUTE_PROBE=0`. The RAR run enabled the guarded anchor-recompute probe with a fresh event log. The default server reported 21,024 GPU KV tokens and reached `GPU KV cache usage: 88.3%`, with running and waiting requests, so this is active KV pressure rather than a client-only queue test.

## Results

| Run | Completed | Mean latency | Max latency | RAR events | Suffix blocks freed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Default disabled | 12 / 12 | 14,692.706 ms | 21,354.411 ms | 0 | 0 |
| RAR enabled | 12 / 12 | 16,229.469 ms | 25,447.512 ms | 12 | 1,080 |

RAR generated 12 observed events with positive free-block deltas, but it increased mean and maximum latency under this frozen configuration. Both runs completed all requests; therefore there is no completion lift, capacity-failure reduction, or goodput improvement claim.

## Interpretation

This is a causal A/B with process isolation, unlike the earlier endpoint-global probe. It verifies the physical action and gives a negative systems result: the current fixed `anchor_token_end=256` policy is too aggressive for this workload. The scheduler can queue requests while preserving completion, so this configuration is high KV pressure but not yet a completion cliff.

The next capacity experiment must calibrate a regime with default preemption, timeout, or failure before evaluating a risk-aware trigger. The policy should be triggered by observed block pressure and SLO slack, not unconditionally once a request reaches a fixed anchor.
