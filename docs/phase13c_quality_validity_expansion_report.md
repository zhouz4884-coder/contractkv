# Phase 13C-1 Quality Validity Expansion

## Scope

This run expands the Phase 13B-Q fresh policy-aligned quality replay from 3 to 20 samples per task:

```text
RULER niah_single_1: 20
LongBench hotpotqa: 20
LongBench qasper: 20
LongBench narrativeqa: 20
RepoBench python_repository_completion: 20
```

There are 100 samples and four policies, producing 400 fresh Qwen3-8B generations. The endpoint was vLLM 0.10.2 on Qwen3-8B. The context-safe protocol uses the same 2600-word bound and `max_tokens=96` for every policy.

## Artifacts

```text
results/end_to_end/phase13c_quality_raw_v0.jsonl
results/end_to_end/phase13c_quality_summary_v0.csv
results/end_to_end/phase13c_quality_enriched_raw_v0.jsonl
results/end_to_end/phase13c_quality_enriched_summary_v0.csv
scripts/phase13c_quality_analysis.py
tests/test_phase13c_quality_analysis.py
```

The enriched table adds signed quality delta, paired win/tie/loss, deterministic bootstrap 95% intervals, dependency-violation counts, and RepoBench Python parse/compile/edit-similarity metrics.

## Results

| Task | Policy | Mean score | Signed delta vs raw | Wins / ties / losses | Dependency violations |
| --- | --- | ---: | ---: | --- | ---: |
| RULER niah | raw-order | 1.000000 | 0.000000 | baseline | 0 |
| RULER niah | CAPOSC | 1.000000 | 0.000000 | 0 / 20 / 0 | 0 |
| LongBench hotpotqa | raw-order | 0.302964 | 0.000000 | baseline | 0 |
| LongBench hotpotqa | CAPOSC | 0.300400 | -0.002564 | 3 / 13 / 4 | 0 |
| LongBench qasper | raw-order | 0.393619 | 0.000000 | baseline | 0 |
| LongBench qasper | CAPOSC | 0.356028 | -0.037591 | 2 / 12 / 6 | 0 |
| LongBench narrativeqa | raw-order | 0.124312 | 0.000000 | baseline | 0 |
| LongBench narrativeqa | CAPOSC | 0.129505 | +0.005193 | 3 / 15 / 2 | 0 |
| RepoBench Python | raw-order | 0.262494 | 0.000000 | baseline | 0 |
| RepoBench Python | CAPOSC | 0.312494 | +0.050000 | 8 / 9 / 3 | 0 |
| RepoBench Python | canonical-all | 0.262068 | -0.000426 | 8 / 8 / 4 | 20 |
| RepoBench Python | static-POSC | 0.267418 | +0.004924 | 7 / 10 / 3 | 0 |

The full policy/task table is in the enriched summary CSV. `canonical-all` produces 20/20 RepoBench dependency-violation rows; the task score alone does not detect all semantic-order failures, so structural validity remains a hard deployment gate.

## Interpretation

The expanded run supports a narrower claim than “CAPOSC is universally quality-preserving”:

1. CAPOSC preserves all declared dependencies in the 20-sample RepoBench subset and improves its mean sanity score over raw-order by `+0.050000` under this protocol.
2. CAPOSC has a measurable negative signed delta on Qasper (`-0.037591`), exceeding the 0.03 local sanity threshold. This is a real quality-risk signal and prevents a blanket no-loss claim across LongBench.
3. RULER remains unchanged, and NarrativeQA has a small positive delta, but these results do not erase the Qasper regression.
4. The old RepoBench `0.333333` drop was an attribution error from the Phase 12C unrestricted canonical-slot projection. The expanded fresh run does not reproduce that number for CAPOSC.

## Metric boundaries

The score is answer containment/token-F1 sanity, not official LongBench or RepoBench scoring. RepoBench parse/compile/edit similarity are additional diagnostics, not a substitute for executable repository tests. The 2600-word bound and prompt wrapper are fixed across policies within this run, but they differ from the older Phase 12C protocol; therefore the old raw score `0.407407` and this run's raw score `0.262494` must not be compared as an algorithm effect without a protocol-matched audit.

## Decision

Phase 13C-1 passes as a validity expansion, not as a universal quality proof. The next quality action should be task-aware contract refinement for Qasper and a larger/order-sensitive RepoBench evaluation. The separate system action is a live capacity-cliff sweep for RAR; current Phase 13B completion data do not yet prove that RAR improves live completion or capacity failures.
