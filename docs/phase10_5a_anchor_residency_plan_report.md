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

Phase 10.5A now records two planner views:

```text
eviction_strict: suffix release is treated as semantic drop/truncation
rar_exact: suffix KV is released, suffix text is preserved, suffix is exactly recomputed
```

This distinction matters because Phase 10.2 eviction/truncation risks measure semantic deletion, not exact KV residency release.

The planner maximizes:

```text
anchor_utility = reclaimed_blocks / max(estimated_recompute_ms, 1)
```

subject to:

```text
estimated action-conditioned risk <= threshold
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
eviction_strict release candidates: 0
eviction_strict keep full request: 140
rar_exact release candidates: 122
rar_exact keep full request: 18
rar_exact average reclaimed blocks over all traces: 531.52
rar_exact average reclaimed blocks among release candidates: 609.94
rar_exact estimated recompute tokens saved vs full recompute: 50,755
```

The machine-readable comparison is:

```text
results/hard_systems/anchor_residency_plan_comparison_v0.csv
```

## Interpretation

The earlier `2/140` observation was the right warning sign: the v0 planner was treating suffix release too much like semantic eviction. After tightening `DROP_FORBIDDEN_TYPES` for pure eviction, the `eviction_strict` view becomes even clearer:

```text
pure eviction/drop is not a viable safe action for this workload
```

For `rar_exact`, those same high-risk RULER and LongBench segments are no longer locked out, because the text is not deleted and the suffix is exactly recomputed. This changes the candidate coverage from `0/140` to `122/140`.

This is the core design-space finding:

```text
traditional eviction view:不可删除 -> 不可释放
ContractKV recoverability view:不可删除 -> 可释放但必须重算
```

## Boundary

This phase still does not claim system benefit. It proves that the corrected RAR-exact planner exposes enough candidate coverage for Phase 10.5C pressure testing. Pressure benefit still requires real vLLM workload evidence.

## Decision For 10.5C

Use four policies:

```text
vLLM-default
vLLM-full-recompute
greedy-rar-exact
ContractKV-RAR-exact
```

The main attribution target is RAR-exact, not KIVI/offload. Low-bit quantization and host offload should remain Phase 11 action-space expansion so the Phase 10.5 hard-system result has clean attribution.
