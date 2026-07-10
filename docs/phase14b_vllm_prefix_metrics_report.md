# Phase 14B vLLM Prefix-Metrics Instrumentation Report

## Goal

Phase 14B moves ContractKV's prefix-cache argument from client timing inference to a guarded, read-only vLLM V1 scheduler observation. It joins server-issued request IDs across:

```text
OpenAI stream timing
ContractKV ledger estimates
V1 scheduler prefix/block observations
```

The probe is enabled only with:

```bash
export CONTRACTKV_PREFIX_METRICS=1
export CONTRACTKV_PREFIX_METRICS_LOG=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/hard_systems/phase14b_prefix_metrics_events_v0.jsonl
```

It changes no scheduler decision, block allocation, or model output.

## Setup

```text
model: Qwen3-8B
backend: vLLM 0.10.2 V1
max_model_len: 8192
max_num_seqs: 8
gpu_memory_utilization: 0.78
prefix cache: enabled
workload: 36 multi-turn agent turns x 3 layouts = 108 live requests
layouts: raw-order, static POSC, CAPOSC
```

The V1 probe records the initial scheduler-visible computed prompt tokens as `prefix_hit_tokens`, sums prompt-only scheduled tokens as `new_prefill_tokens`, and joins them to the OpenAI `chatcmpl-*` request ID. Reused and newly allocated physical block counts are documented scheduler derivations, not hidden cache-manager counters.

## Probe Gate

A repeated 6021-token stable-context smoke test establishes the physical signal before the policy replay:

| repeated request | observed prefix hit | observed new prefill | TTFT |
| --- | ---: | ---: | ---: |
| first | 0 | 6021 | 1619.653 ms |
| second, identical prompt | 6016 | 5 | 69.653 ms |

This is direct V1 scheduler evidence that the second request reuses almost all cached prompt work.

## Live Joined Results

All 108 API records joined one-to-one with V1 observations.

| layout | joined | mean TTFT | p95 TTFT | mean observed prefix hit | mean observed new prefill | mean estimated new prefill |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| raw-order | 36/36 | 113.147 ms | 241.277 ms | 360.889 | 344.556 | 276.944 |
| static POSC | 36/36 | 88.345 ms | 165.865 ms | 467.556 | 237.889 | 200.278 |
| CAPOSC | 36/36 | 46.637 ms | 74.639 ms | 656.000 | 49.333 | 181.667 |

Relative to raw-order, CAPOSC reduces mean TTFT by 58.8%, p95 TTFT by 69.1%, and scheduler-observed new prefill tokens by 85.7%. The quality-marker sanity rate is 1.0 for all three layouts in this controlled workload.

Within every fixed layout, observed new-prefill tokens strongly track real TTFT:

| layout | Pearson(observed new prefill, TTFT) |
| --- | ---: |
| raw-order | 0.987 |
| static POSC | 0.995 |
| CAPOSC | 0.981 |

This establishes the intended mechanism: CAPOSC selects layouts with more actual cached prompt work and less actual new prefill. It is stronger than a client-only timing claim.

## Calibration Boundary

The ledger estimate is useful but is not a universal real-time predictor. Its correlation with observed new prefill is strong for raw-order (0.998) and static POSC (0.834), but negative for adaptive CAPOSC (-0.209). CAPOSC changes layout according to prior cache state, while the scheduler sees global cache and scheduling effects; the ledger must therefore be described as a compiler signal, not an exact cache-hit oracle.

The V1 scheduler does not expose prefix-cache eviction counts or worker-level prefill/decode GPU times through this read-only probe. Those fields remain null/unavailable. No result here claims a direct eviction count, GPU kernel time, or arbitrary physical-block attribution.

## Artifacts

```text
scripts/install_vllm_v1_prefix_metrics_probe.py
scripts/summarize_vllm_prefix_metrics.py
scripts/join_phase14b_prefix_metrics.py
scripts/phase14b_prefix_metrics_smoke.py

results/hard_systems/phase14b_prefix_metrics_events_v0.jsonl
results/hard_systems/phase14b_prefix_metrics_summary_v0.csv
results/hard_systems/phase14b_live_layout_raw_v0.jsonl
results/hard_systems/phase14b_live_layout_summary_v0.csv
results/hard_systems/phase14b_live_prefix_join_v0.csv
results/hard_systems/phase14b_live_prefix_join_summary_v0.csv
results/hard_systems/phase14b_ledger_ttft_correlation_v0.csv
```

## Decision

Phase 14B passes the prefix-mechanism gate. The next phase is not another timing replay: it is held-out, generic QC calibration for the compiler decision before using CAPOSC in a larger mixed-workload live evaluation.
