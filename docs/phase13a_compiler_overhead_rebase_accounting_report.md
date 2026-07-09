# Phase 13A Compiler Overhead and Rebase Accounting Report

## Goal

Phase 13A answers two small but important questions left by Phase 12:

```text
1. Is CAPOSC compiler overhead small relative to real TTFT?
2. Did the current rebase heuristic actually trigger, or was "rebase-mode" only a policy label?
```

This is a local microbenchmark, not a new vLLM serving experiment.

## Artifacts

```text
scripts/phase13a_compiler_overhead.py
tests/test_phase13a_compiler_overhead.py

results/prefix_cache/phase13a_compiler_overhead_raw_v0.csv
results/prefix_cache/phase13a_compiler_overhead_summary_v0.csv
results/prefix_cache/phase13a_rebase_accounting_v0.csv
```

## Method

The benchmark replays the 36-turn Phase 12 trajectory set through the CAPOSC compiler:

```text
36 trajectory turns
1000 repeats
36000 total compiles
```

Each compile records:

```text
compile_ms
ledger_lookup_ms
candidate_eval_ms
candidate_count
selected_policy
rebase_triggered
rebase_hidden_by_slack
rebase_overhead_ms
```

## Compiler Overhead Result

| metric | value |
|---|---:|
| num compiles | 36000 |
| compile mean | 0.388654 ms |
| compile p50 | 0.311500 ms |
| compile p95 | 0.818500 ms |
| ledger lookup mean | 0.248554 ms |
| ledger lookup p95 | 0.507225 ms |
| candidate eval mean | 0.159045 ms |
| candidate eval p95 | 0.319600 ms |
| candidate count mean | 5.000000 |

Compared with Phase 12F real vLLM CAPOSC+rebase timing:

```text
Phase 12F CAPOSC+rebase mean TTFT = 42.278 ms
Phase 12F CAPOSC+rebase p95 TTFT = 48.697 ms

compiler mean / mean TTFT = 0.92%
compiler p95 / p95 TTFT = 1.68%
```

So the compiler overhead is comfortably below real serving latency.

## Rebase Accounting Result

| metric | value |
|---|---:|
| num compiles | 36000 |
| rebase_triggered_count | 0 |
| rebase_hidden_by_slack_count | 0 |
| rebase_selected_fraction | 0.000000 |
| rebase_hidden_fraction | 0.000000 |
| rebase_overhead_ms_mean | 0.000000 |
| rebase_overhead_ms_p95 | 0.000000 |

Selected policy counts:

```json
{
  "boolean-guarded": 2000,
  "cache-aware-posc": 26000,
  "posc": 8000
}
```

This is an important correction:

```text
The current CAPOSC rebase heuristic did not trigger on the Phase 12 workload.
```

Therefore, Phase 12F/12G's `CAPOSC + rebase` label should not be described as proof that an explicit rebase actuator fired. It should be treated as a rebase-mode replay label, with explicit rebase accounting now showing zero triggered rebase events under the current heuristic.

## Interpretation

The overhead result is strong:

```text
compiler overhead << TTFT saving / serving latency
```

The rebase result is a useful guardrail:

```text
rebase is not free magic;
it must be counted as an explicit layout/cache-warmup event.
```

Current status:

```text
CAPOSC itself is implemented and measured.
Rebase accounting is implemented.
Actual rebase trigger coverage is zero on this workload.
```

## What Remains

The remaining Phase 13 items are:

```text
1. Rebase stress workload:
   construct trajectories where static rebase has amortized future benefit and enough tool slack.

2. Real task quality:
   run a small RULER / LongBench / RepoBench / mixed-agent subset with real scoring,
   not only marker/order sanity.

3. Paper wording:
   define oracle-best-layout as offline upper bound only.
   define LCP as useful compiler signal, not a complete TTFT predictor.
```

## Decision

Phase 13A should be cited as an appendix-style systems sanity check:

```text
CAPOSC's Python compiler overhead is sub-millisecond on the evaluated traces.
The current rebase heuristic did not trigger, so rebase requires a separate stress experiment before being claimed as an active mechanism.
```
