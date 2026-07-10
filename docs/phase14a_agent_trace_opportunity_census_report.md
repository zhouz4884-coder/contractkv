# Phase 14A Agent Trace Opportunity Census

## Scope

Phase 14A performs an offline compiler census before spending more GPU time. It creates 500 multi-turn agent requests, with 100 turns in each family:

```text
code_agent: RepoBench-backed repository context
rag_agent: LongBench HotpotQA-backed retrieval context
structured_document_qa: LongBench Qasper-backed scientific documents
tool_function_agent: stable tool schema/manual plus volatile observations
mixed_long_history_agent: ordered cross-turn history plus volatile observations
```

Each source sample is replayed for five turns, so source-backed contexts remain stable while observations vary. This measures opportunity rather than model output quality.

## Coverage Results

| Family | Turns | Opportunity coverage | Safe canonicalization coverage | Median potential reusable-prefix gain | Raw fallback rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| code agent | 100 | 0.00 | 0.00 | 0.0 | 0.00 |
| RAG agent | 100 | 1.00 | 0.70 | 15474.5 | 0.30 |
| structured-document QA | 100 | 1.00 | 0.00 | 5736.0 | 1.00 |
| tool/function agent | 100 | 1.00 | 1.00 | 380.0 | 0.00 |
| mixed long-history agent | 100 | 1.00 | 1.00 | 490.0 | 0.00 |

Four of five families have legal nonzero prefix opportunity. Three families have nonzero safe canonicalization coverage. Code context is deliberately modeled as a strict ordered component, so no legal reordering opportunity is claimed. Structured documents have high potential gain but are conservatively routed to QC fallback under the current ordered-discourse risk rule.

## What Is Measured

Every turn records:

```text
stable and volatile segment tokens
raw prefix reuse tokens
maximum legal POSC prefix tokens
CAPOSC expected prefix gain
partial-canonical eligibility
hard-order-sensitive flag
QC risk bucket and raw-fallback decision
```

The key distinction is between opportunity and safe coverage. A document may have a large legal prefix gain yet still be sent to raw order if its ordered-discourse risk is high. This is the desired fail-closed behavior, not a missing data point.

## Gate

The requested Phase 14A gate passes for the census definition: more than half of turns have legal nonzero opportunity, and three workload families have clear safe opportunity. This is offline evidence only. It does not claim real vLLM cache hits, task-quality preservation, or serving goodput.

## Artifacts

```text
results/workload/phase14a_agent_traces_v0.jsonl
results/workload/phase14a_opportunity_census_raw_v0.csv
results/workload/phase14a_opportunity_census_summary_v0.csv
scripts/phase14a_agent_trace_census.py
tests/test_phase14a_agent_trace_census.py
```

## Next

Phase 14B instruments vLLM internals per request so the same ledger metrics can be compared to observed prefix-hit tokens, new-prefill work, block allocation, and scheduler waiting time.
