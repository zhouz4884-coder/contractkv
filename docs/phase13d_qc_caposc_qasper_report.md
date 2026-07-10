# Phase 13D-A Risk-Constrained CAPOSC on Ordered Documents

## Motivation

Phase 13C found a negative Qasper CAPOSC delta with a bootstrap interval below zero, while all hard dependency edges remained valid. The per-sample audit found the same layout change on every Qasper sample:

```text
[SYS, TOOL_OBS, RAG_CHUNK, USER_QUERY]
->[SYS, RAG_CHUNK, TOOL_OBS, USER_QUERY]
```

This establishes that hard precedence legality alone is insufficient for behavioral equivalence.

## QC-CAPOSC contract

QC-CAPOSC introduces an `ordered_discourse_component` feature. It is computed from the text actually retained after truncation, using section headings and scientific-discourse cues such as `this paper`, `we propose`, `our method`, and `experimental results`. It does not inspect the dataset or task name.

For each candidate layout it records:

```text
hard_edge_valid
adjacency_preservation_ratio
relative_order_edit_distance
ordered_document_heading_count
layout_risk_mean
layout_risk_upper_bound
```

If the risk upper bound exceeds `epsilon=0.03`, QC-CAPOSC falls back to raw order. This is a candidate-level no-regret fallback because raw order remains in the feasible set.

## Fresh replay

The fresh Qwen3-8B replay uses 20 Qasper samples and compares raw-order, CAPOSC, and QC-CAPOSC.

```text
QC fallback count: 20 / 20
QC raw prompt-hash matches: 20 / 20
QC raw output matches: 20 / 20
```

The prompt and output equality is the main result: QC-CAPOSC did not merely obtain a similar score; it selected an identical raw layout and therefore preserved the raw behavior exactly for every risk-flagged sample.

The fresh CAPOSC score in this small replay is higher than raw, unlike the earlier 400-generation run. That direction change confirms output-level variation remains material; it must not be used to overturn the Phase 13C paired risk finding. QC-CAPOSC is justified by deterministic layout equivalence under high risk, not by claiming a new quality gain.

## Boundary

This implements a generic ordered-discourse risk signal, but it is only validated on Qasper so far. The next expansion should apply the same feature to other structured-document and multi-hop workloads, then calibrate `RiskUCB` from held-out paired outcomes rather than the current fixed conservative bound.
