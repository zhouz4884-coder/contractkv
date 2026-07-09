# Phase 12D POSC Layout Compiler Report

## Goal

Phase 12D upgrades the Phase 12C layout guard into a compiler abstraction:

```text
Partial-Order Segment Contract (POSC)
```

The goal is not to hard-code:

```text
if task == code: raw
else: canonical
```

Instead, ContractKV represents prompt layout as a dependency DAG:

```text
A -> B means segment A must appear before segment B.
```

The compiler then performs a prefix-maximizing topological sort:

```text
maximize stable/cacheable prefix tokens
subject to no dependency-edge violation
```

This makes canonical-slot a guarded compiler optimization rather than a prompt-order trick.

## Artifacts

```text
scripts/phase12_posc_layout_compiler.py
scripts/phase12d_mixed_agent_task_builder.py
scripts/phase12d_guarded_layout_replay.py
tests/test_phase12_posc_layout_compiler.py

results/prefix_cache/phase12d_mixed_agent_cases_v0.jsonl
results/prefix_cache/phase12d_posc_layout_decisions_v0.jsonl
results/prefix_cache/phase12d_guarded_replay_raw_v0.jsonl
results/prefix_cache/phase12d_guarded_replay_summary_v0.csv
results/prefix_cache/phase12d_posc_quality_summary_v0.csv
```

## POSC Contract

Each segment carries contract metadata:

```json
{
  "segment_id": "repo_class",
  "segment_type": "REPO_CLASS",
  "token_count": 96,
  "dependencies": ["repo_import"],
  "volatility": 0.0,
  "cache_stability": 1.0,
  "stability_scope": "cross_turn"
}
```

The compiler can move a stable code component before dynamic tool observations, but it cannot reorder the component internally:

```text
valid POSC:
  [SYS][REPO_IMPORT][REPO_CLASS][REPO_FUNCTION][TOOL_OBS][QUERY]

invalid canonical-all:
  [SYS][REPO_FUNCTION][REPO_CLASS][REPO_IMPORT][TOOL_OBS][QUERY]
```

## Mixed-Agent Workload

Phase 12D builds 30 mixed-agent cases:

```text
10 code + tool observation cases
10 RAG + tool observation cases
10 repo + document + tool observation cases
```

Each case has an explicit dependency DAG. Code cases include:

```text
repo_import -> repo_class -> repo_function -> query
tool_obs -> query
```

The money case is:

```text
raw-order:
  [SYS][TOOL_OBS][REPO_IMPORT][REPO_CLASS][REPO_FUNCTION][QUERY]

canonical-all:
  may put function/class before import, creating violated_edges

POSC:
  [SYS][REPO_IMPORT][REPO_CLASS][REPO_FUNCTION][TOOL_OBS][QUERY]
```

## Real vLLM Result

Model and serving setup:

```text
Qwen3-8B
vLLM 0.10.2
prefix cache enabled
max_model_len = 8192
max_num_seqs = 2
150 total requests = 30 cases * 5 policies
```

SLO = 700 ms summary:

| policy | quality score | quality drop | mean TTFT | p95 TTFT | SLO req/s | canonicalized fraction | fallback fraction | violated edge cases |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| raw-order | 1.000000 | 0.000000 | 75.110 ms | 70.822 ms | 3.307 | 0.000 | 1.000 | 0 |
| canonical-all | 0.666667 | 0.333333 | 53.729 ms | 69.965 ms | 3.560 | 0.667 | 0.000 | 10 |
| boolean-guarded | 1.000000 | 0.000000 | 38.384 ms | 42.742 ms | 3.774 | 0.333 | 0.667 | 0 |
| POSC | 1.000000 | 0.000000 | 47.366 ms | 69.767 ms | 3.650 | 1.000 | 0.000 | 0 |
| POSC + anchors | 1.000000 | 0.000000 | 66.511 ms | 81.570 ms | 3.400 | 1.000 | 0.000 | 0 |

Case-type quality:

| policy | code_tool | rag_tool | repo_doc_tool |
|---|---:|---:|---:|
| raw-order | 1.000 | 1.000 | 1.000 |
| canonical-all | 0.000 | 1.000 | 1.000 |
| boolean-guarded | 1.000 | 1.000 | 1.000 |
| POSC | 1.000 | 1.000 | 1.000 |
| POSC + anchors | 1.000 | 1.000 | 1.000 |

## What This Proves

Phase 12D turns the Phase 12C negative RepoBench result into a control-plane result.

```text
canonical-all:
  creates 10 dependency-violating code layouts and fails quality.

boolean-guarded:
  is safe, but falls back to raw order for code-containing cases.

POSC:
  preserves dependency order, canonicalizes all 30 mixed-agent cases,
  and keeps quality score at 1.0.
```

The key distinction is that POSC does not ask whether a task is globally reorderable. It asks which segment orderings are legal under the dependency DAG.

This is the compiler value:

```text
raw-order is safe but conservative.
canonical-all is aggressive but unsafe.
boolean guard is safe but coarse.
POSC is dependency-aware and can produce partial-canonical layouts.
```

## Structural Anchors

`POSC + anchors` injects deterministic segment boundaries:

```text
[SEGMENT type="REPO_CLASS" id="repo_class"]
...
[/SEGMENT]
```

In this mixed-agent replay, anchors preserved quality but added an average of 34 tokens, increasing mean TTFT from 47.366 ms to 66.511 ms. This means anchors are useful as a robustness mechanism, but should be applied selectively when boundary sensitivity is detected.

## Boundaries

This is a mixed-agent sanity benchmark, not official LongBench or RepoBench scoring.

The Phase 12D quality score is strict:

```text
any violated dependency edge => quality failure
otherwise marker/order sanity is checked against model output
```

This is intentional. A layout that violates POSC may be semantically unsafe even if the model occasionally guesses the marker.

Phase 12D still does not claim arbitrary non-linear KV stitching or RoPE-corrected segment grafting. It is a real vLLM prompt-layout compiler result.

## Decision

Phase 12D supports this paper claim:

```text
ContractKV compiles prompt segments under partial-order contracts to maximize cache-stable prefix reuse while preserving semantic dependencies.
```

The next phase should evaluate a guarded POSC compiler on larger real agent traces, using POSC to decide when canonical slots, raw order, and structural anchors are each appropriate.
