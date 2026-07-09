# Phase 13: End-to-End ContractKV Under Heterogeneous Agent Serving

## Goal

Phase 13 moves beyond isolated mechanism tests and asks whether three ContractKV mechanisms compose into an end-to-end serving control plane:

```text
CAPOSC: prefix-cache-aware segment layout for low/normal load.
SSPP: tool-slack segment preparation hiding.
RAR: block-pressure residency/recompute rescue.
```

This first Phase 13 artifact is a ledger replay, not a fresh live vLLM run. It reuses the validated CAPOSC compiler, the SSPP slack accounting model, and RAR block-pressure accounting in one common workload and metric schema.

## Workload

The replay builds 60 heterogeneous agent turns:

```text
code_agent: 12 turns
rag_agent: 12 turns
mixed_agent: 12 turns
tool_call_agent: 12 turns
long_history_agent: 12 turns
```

Arrival modes:

```text
concurrency = 1: sequential_session_replay
concurrency = 2 / 4 / 6 / 8: concurrent_multi_session_replay
```

SLO buckets:

```text
100 ms, 200 ms, 500 ms, 700 ms, 1000 ms
```

## Policies

Phase 13A compares the four main policies requested for end-to-end serving:

```text
vLLM raw-order
ContractKV-CAPOSC
ContractKV-CAPOSC + SSPP
ContractKV-CAPOSC + SSPP + RAR
```

Boolean-guarded and oracle-best remain useful ablations from Phase 12, but they are not the main Phase 13 baseline.

## Key Results

At SLO = 500 ms:

| concurrency | policy | SLO req/s | mean TTFT ms | p95 TTFT ms | completion | capacity failures | SSPP hidden | RAR events | blocks freed | recompute tokens saved |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | vLLM raw-order | 5.139015 | 69.789833 | 142.285000 | 1.000000 | 0 | 0.000000 | 0 | 0 | 0 |
| 1 | ContractKV-CAPOSC | 5.367667 | 61.500667 | 97.480000 | 1.000000 | 0 | 0.000000 | 0 | 0 | 0 |
| 1 | CAPOSC + SSPP | 6.662721 | 25.288833 | 107.027000 | 1.000000 | 0 | 0.764919 | 0 | 0 | 0 |
| 1 | CAPOSC + SSPP + RAR | 6.662721 | 25.288833 | 107.027000 | 1.000000 | 0 | 0.764919 | 0 | 0 | 0 |
| 4 | vLLM raw-order | 3.688814 | 92.289833 | 164.785000 | 1.000000 | 0 | 0.000000 | 0 | 0 | 0 |
| 4 | ContractKV-CAPOSC | 3.805165 | 84.000667 | 119.980000 | 1.000000 | 0 | 0.000000 | 0 | 0 | 0 |
| 4 | CAPOSC + SSPP | 4.692077 | 34.325233 | 129.527000 | 1.000000 | 0 | 0.764919 | 0 | 0 | 0 |
| 4 | CAPOSC + SSPP + RAR | 4.675106 | 35.098900 | 133.477000 | 1.000000 | 0 | 0.764919 | 48 | 680 | 12424 |
| 8 | vLLM raw-order | 2.707324 | 118.568421 | 150.378750 | 0.633333 | 22 | 0.000000 | 0 | 0 | 0 |
| 8 | ContractKV-CAPOSC | 2.742340 | 113.852105 | 146.318750 | 0.633333 | 22 | 0.000000 | 0 | 0 | 0 |
| 8 | CAPOSC + SSPP | 3.072722 | 74.644316 | 160.184150 | 0.633333 | 22 | 0.764919 | 0 | 0 | 0 |
| 8 | CAPOSC + SSPP + RAR | 3.211150 | 60.614893 | 163.477000 | 0.933333 | 4 | 0.764919 | 48 | 680 | 12424 |

## Interpretation

CAPOSC alone improves the low/normal-load prefix-cache ledger signal:

```text
concurrency 1, SLO 500 ms:
  raw-order SLO req/s = 5.139015
  CAPOSC SLO req/s = 5.367667
  raw-order p95 TTFT = 142.285 ms
  CAPOSC p95 TTFT = 97.480 ms
```

SSPP adds a separate effect: it hides preparation work inside tool slack. In this replay, the mean hidden fraction is:

```text
SSPP hidden fraction mean = 0.764919
```

This reduces mean TTFT substantially in low and medium load:

```text
concurrency 4:
  CAPOSC mean TTFT = 84.000667 ms
  CAPOSC + SSPP mean TTFT = 34.325233 ms
```

RAR is mostly inactive until block pressure appears. At concurrency 8, it is the mechanism that changes completion behavior:

```text
vLLM raw-order:
  completion rate = 0.633333
  capacity failures = 22

CAPOSC + SSPP + RAR:
  completion rate = 0.933333
  capacity failures = 4
  RAR events = 48
  blocks freed = 680
  recompute tokens saved = 12424
```

This matches the intended decomposition:

```text
CAPOSC helps prefix/cache layout.
SSPP hides predictable preparation under slack.
RAR matters under block pressure.
```

## Quality And Overhead

All Phase 13A rows have:

```text
quality_bad_rate = 0
```

This is layout/order sanity, not official task scoring. Phase 13B should include real vLLM output scoring on the same heterogeneous workload.

Compiler overhead is already bounded by Phase 13A overhead accounting:

```text
compiler mean = 0.388654 ms
compiler p95 = 0.818500 ms
compiler mean / Phase 12F mean TTFT = 0.92%
compiler p95 / Phase 12F p95 TTFT = 1.68%
```

## Claim Boundary

Phase 13A does not claim:

```text
fresh live vLLM goodput,
real prefix-cache hit-rate counters,
real KV swap/offload,
production throughput.
```

It does claim:

```text
the ContractKV control plane can compose CAPOSC, SSPP, and RAR into a common end-to-end serving ledger;
each mechanism contributes in the load regime it was designed for;
the unified metric schema can now drive Phase 13B live vLLM replay.
```

## Artifacts

```text
scripts/phase13_heterogeneous_serving.py
tests/test_phase13_heterogeneous_serving.py
results/end_to_end/phase13_heterogeneous_serving_raw_v0.csv
results/end_to_end/phase13_heterogeneous_serving_summary_v0.csv
results/end_to_end/phase13_heterogeneous_serving_case_summary_v0.csv
```

## Next

Phase 13B should run the same four policies against a live vLLM endpoint:

```text
vLLM raw-order
ContractKV-CAPOSC
ContractKV-CAPOSC + SSPP
ContractKV-CAPOSC + SSPP + RAR
```

The live run should preserve the same fields and add:

```text
real request_id
real TTFT / TPOT / total latency
real model output
real quality score
GPU memory samples
vLLM prefix-cache or scheduler counters if observable
```
