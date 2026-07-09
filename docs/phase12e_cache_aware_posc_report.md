# Phase 12E Cache-Aware POSC Report

## Goal

Phase 12D showed that POSC is safer than `canonical-all`, but the result also exposed a subtle systems problem:

```text
static POSC can be slower than boolean-guarded when it breaks a de facto cached prefix
```

The cause is that Phase 12D optimized only the current prompt DAG. It did not know what layout vLLM had already cached in previous turns.

Phase 12E upgrades POSC into:

```text
Cache-Aware POSC (CAPOSC)
```

The compiler now uses a `Segment Prefix Ledger`:

```text
previous segment order
segment id
segment content hash
token count
selected layout policy
```

It then selects among valid candidates:

```text
raw-order
boolean-guarded
static POSC
cache-preserving POSC
cache-aware POSC + optional rebase
```

The selector is no-regret in the ledger model because `boolean-guarded` is included in the candidate set. Therefore, the selected layout should not have more estimated new-prefill tokens than boolean-guarded under the same visible cache ledger.

## Artifacts

```text
scripts/phase12e_cache_aware_posc.py
scripts/phase12e_multiturn_trajectory_builder.py
scripts/phase12e_multiturn_replay.py
tests/test_phase12e_cache_aware_posc.py

results/prefix_cache/phase12e_multiturn_trajectories_v0.jsonl
results/prefix_cache/phase12e_cache_aware_layout_decisions_v0.jsonl
results/prefix_cache/phase12e_multiturn_replay_raw_v0.jsonl
results/prefix_cache/phase12e_multiturn_replay_summary_v0.csv
results/prefix_cache/phase12e_multiturn_case_summary_v0.csv
```

## Algorithm

CAPOSC solves:

```text
maximize reusable prefix tokens and future stable-prefix value
subject to:
  dependency DAG is valid
  no violated POSC edges
  selected layout is available in candidate set
```

The key difference from static POSC is:

```text
static POSC:
  maximize stable prefix in the current DAG

CAPOSC:
  maximize LCP against current cache state first,
  then account for future stable-prefix value
```

This handles the failure case:

```text
previous cached layout:
  [SYS][REPO_IMPORT][REPO_CLASS][TOOL_OBS][QUERY]

current static POSC:
  [SYS][REPO_IMPORT][REPO_CLASS][REPO_FUNCTION][TOOL_OBS][QUERY]

CAPOSC:
  keeps the longest legal cached prefix when it is beneficial,
  or rebases to a better stable layout only when amortized benefit exceeds rebase cost.
```

## Multi-Turn Replay Setup

The replay uses 36 trajectory turns:

```text
2 code-agent trajectories * 6 turns
2 RAG-agent trajectories * 6 turns
2 mixed-agent trajectories * 6 turns
```

Each turn is evaluated under five policies:

```text
raw-order
boolean-guarded
posc
cache-aware-posc
cache-aware-posc-rebase
```

This produces:

```text
180 raw records
30 SLO summary rows
15 case-type summary rows
```

The replay is a deterministic ledger model:

```text
TTFT is modeled from estimated new-prefill tokens.
estimated_lcp_tokens is computed from ContractKV's segment ledger.
vLLM cached-token hit rate is not claimed here.
```

## Main Result

At SLO = 300 ms:

| policy | quality | mean TTFT | p95 TTFT | SLO req/s | mean LCP tokens | mean new-prefill tokens |
|---|---:|---:|---:|---:|---:|---:|
| raw-order | 1.000000 | 82.621 ms | 160.308 ms | 6.890 | 247.056 | 276.944 |
| boolean-guarded | 1.000000 | 81.510 ms | 156.808 ms | 6.943 | 247.056 | 276.944 |
| POSC | 1.000000 | 72.710 ms | 112.913 ms | 7.395 | 323.722 | 200.278 |
| CAPOSC | 1.000000 | 70.186 ms | 116.198 ms | 7.536 | 342.333 | 181.667 |
| CAPOSC + rebase | 1.000000 | 71.186 ms | 117.198 ms | 7.479 | 342.333 | 181.667 |

CAPOSC improves estimated LCP over boolean-guarded:

```text
247.056 -> 342.333 tokens
```

and reduces estimated new-prefill work:

```text
276.944 -> 181.667 tokens
```

The modeled p95 TTFT drops:

```text
boolean-guarded p95 = 156.808 ms
CAPOSC p95 = 116.198 ms
relative reduction = 25.9%
```

## Case-Type Breakdown

### Code-Agent

The code-agent trajectory is the strongest "dynamic observation shreds prefix" case.

| policy | mean TTFT | p95 TTFT | mean LCP | mean new-prefill |
|---|---:|---:|---:|---:|
| boolean-guarded | 124.956 ms | 172.835 ms | 9.167 | 556.167 |
| POSC | 86.293 ms | 128.940 ms | 266.667 | 298.667 |
| CAPOSC | 89.710 ms | 125.940 ms | 266.667 | 298.667 |

This shows why POSC is necessary in long agent loops:

```text
raw/boolean preserves order, but volatile tool observations near the front destroy LCP.
POSC/CAPOSC move stable code under valid dependencies, restoring reusable prefix.
```

### Mixed-Agent

Mixed-agent has a de facto cached raw prefix that can be valuable.

| policy | mean TTFT | p95 TTFT | mean LCP | mean new-prefill |
|---|---:|---:|---:|---:|
| boolean-guarded | 56.515 ms | 101.550 ms | 413.667 | 113.000 |
| POSC | 64.778 ms | 105.550 ms | 386.167 | 140.500 |
| CAPOSC | 58.432 ms | 107.600 ms | 413.667 | 113.000 |

This is the important Phase 12E correction:

```text
static POSC can lose to boolean by breaking an already cached layout.
CAPOSC detects that state and keeps the longer LCP instead of blindly canonicalizing.
```

### RAG-Agent

RAG-agent shows CAPOSC can still improve reusable prefix when stable chunks persist across turns:

| policy | mean TTFT | p95 TTFT | mean LCP | mean new-prefill |
|---|---:|---:|---:|---:|
| boolean-guarded | 63.058 ms | 96.675 ms | 318.333 | 161.667 |
| POSC | 67.058 ms | 100.675 ms | 318.333 | 161.667 |
| CAPOSC | 62.417 ms | 108.675 ms | 346.667 | 133.333 |

CAPOSC selected:

```text
cache-aware-posc: 26 cases
posc: 8 cases
boolean-guarded: 2 cases
```

So the policy is not a boolean guard. It is a state-aware candidate selector.

## Answer To "Can POSC Be Faster?"

Yes, but the fast version must be cache-aware.

The correct framing is:

```text
POSC is the semantic safety constraint.
CAPOSC is the cache-state-aware optimizer under that constraint.
```

Static POSC can be slower because it does not know the real cached prefix. Boolean can be accidentally fast because it preserves raw order. CAPOSC makes that accidental behavior explicit and controlled:

```text
if raw/boolean has the best valid LCP, keep it;
if static POSC creates a better stable prefix, use it;
if a one-time rebase is worth it under slack, rebase.
```

## Boundaries

Phase 12E does not claim:

```text
observed vLLM cached-token counts
real vLLM TTFT improvement
production goodput improvement
arbitrary non-linear KV grafting
RoPE-corrected segment stitching
```

It does claim:

```text
CAPOSC fixes the main weakness of static POSC by adding cache-state awareness.
The compiler can choose between raw, boolean, POSC, and cache-preserving layouts.
In the ledger model, CAPOSC improves reusable-prefix tokens while preserving quality.
```

## Decision

Phase 12E should be followed by a real vLLM A/B:

```text
Phase 12F: real vLLM CAPOSC replay
  run the same multi-turn trajectories on Qwen3-8B with prefix cache enabled
  record real TTFT / TPOT / latency
  record vLLM logs and cached-token stats if exposed
  compare boolean-guarded vs static POSC vs CAPOSC
```

The main paper point is now stronger:

```text
ContractKV is not a prompt-engineering heuristic.
It is a segment-layout compiler with semantic partial-order constraints and cache-state-aware optimization.
```
