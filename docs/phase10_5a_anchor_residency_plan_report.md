# Phase 10.5A Anchor Residency Plan Report

## Goal

Build the offline planner for Risk-Anchored Recompute (RAR):

```text
choose a quality-safe anchor boundary
keep high-risk prefix KV resident
release/recompute suffix KV under pressure
preserve suffix text for reconstruction
```

## Inputs

```text
results/workload/agent_trace_v0.jsonl
results/hard_systems/real_quality_risk_summary_qwen3_8b_v0.csv
```

Planner:

```text
scripts/build_anchor_residency_plan.py
```

Output:

```text
results/hard_systems/anchor_residency_plan_v0.jsonl
```

## Method

The planner distinguishes text deletion from KV residency release:

```text
MUST_RESIDENT_TYPES = SYS_PROMPT, TOOL_SCHEMA
MUST_RECONSTRUCT_TYPES = USER_QUERY
DROP_FORBIDDEN_TYPES = SYS_PROMPT, TOOL_SCHEMA, USER_QUERY
```

`USER_QUERY` can appear in the recompute suffix because suffix text is preserved and reconstructed. It is not dropped.

The planner maximizes:

```text
anchor_utility = reclaimed_blocks / max(estimated_recompute_ms, 1)
```

subject to:

```text
estimated quality risk <= threshold
estimated recompute time <= slack or SLO margin
no must-resident segment in suffix
boundary guard enabled
```

Boundary guard:

```text
boundary_guard_tokens = 32
recompute_start_token = anchor_token_end - 32
```

## Results

```text
total traces: 140
release_suffix_candidate: 2
keep_full_request: 138
average reclaimed blocks: 0.94
```

The strict v0 planner is intentionally conservative. It marks only two RepoBench traces as suffix-release candidates:

```text
recomputed_segment_types include CODE_PREFIX and USER_QUERY
dropped_segment_types is always []
```

## Interpretation

This result is useful but also exposes the next bottleneck:

```text
RAR v0 is safe, but candidate coverage is low.
```

RULER and LongBench context segments are high-risk under the real Qwen3-8B risk summary, so the planner refuses to release them. That is the correct conservative behavior for v0.

## Boundary

This phase does not claim system benefit. It only creates the decision substrate for anchored recompute. Pressure benefit requires Phase 10.5C.
