# Phase 12C Real-Task Quality Sanity Report

## Goal

Phase 12C checks the main risk of canonical-slot layout:

```text
Does moving dynamic tool observations after stable context change task semantics?
```

This is a task sanity check, not official LongBench or RepoBench scoring.

Compared layouts:

```text
raw-order + prefix cache
canonical-slot + prefix cache
```

Tasks:

```text
RULER: niah_single_1, 3 samples
LongBench: hotpotqa / qasper / narrativeqa, 3 samples each
RepoBench: python_repository_completion, 3 samples
```

## Artifacts

```text
results/prefix_cache/phase12c_task_quality_raw_v0.jsonl
results/prefix_cache/phase12c_task_quality_summary_v0.csv
logs/phase12/phase12c_prefix_on_qwen3_8b_8014.log
```

## Main Result

| task | raw score | canonical score | quality drop | canonical TTFT reduction |
|---|---:|---:|---:|---:|
| RULER niah_single_1 | 1.000000 | 1.000000 | 0.000000 | 80.097% |
| LongBench hotpotqa | 0.083333 | 0.083333 | 0.000000 | 92.282% |
| LongBench qasper | 0.287742 | 0.272072 | 0.015670 | 92.312% |
| LongBench narrativeqa | 0.104129 | 0.133285 | 0.000000 | 92.255% |
| RepoBench python_repository_completion | 0.407407 | 0.074074 | 0.333333 | 79.720% |

## Interpretation

Canonical-slot passes the quality sanity threshold for RULER and the tested LongBench subset:

```text
RULER drop = 0.000000
hotpotqa drop = 0.000000
qasper drop = 0.015670
narrativeqa drop = 0.000000
```

The qasper drop is within the <= 0.03 sanity threshold. RULER and LongBench therefore support the claim that canonical-slot can reduce TTFT without obvious semantic loss when segment contracts allow reordering.

RepoBench is different:

```text
RepoBench drop = 0.333333
```

This is a useful negative result. Code completion appears order-sensitive in this small sanity set, so canonical-slot must not be applied blindly to code segments.

## Layout Guard

The Phase 12C decision rule is:

```text
only canonicalize layout when segment contract allows reordering;
otherwise preserve raw order.
```

For paper framing, this is not a weakness. It strengthens ContractKV's contract story:

```text
stable document / retrieval context:
  canonical-slot is safe in the tested sanity subset.

code completion context:
  preserve raw order unless a stronger code-specific contract validates reordering.
```

## Boundaries

This report does not claim official LongBench or RepoBench benchmark scores. It uses contains-answer / token-F1 sanity scoring to check whether canonical-slot changes answer behavior relative to raw-order.
