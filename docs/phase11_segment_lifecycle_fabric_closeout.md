# Phase 11 Segment Lifecycle Fabric Closeout

## Scope

Phase 11 extends ContractKV beyond RAR-exact into a broader Segment Lifecycle Fabric:

```text
11A: Segment Radix Forest with canonical slots
11B: SSPP tool-slack preparation
11C: action-conditioned backend stubs for quant/offload attribution
```

Phase 11 is a control-plane characterization phase. It does not claim a real mixed-precision attention kernel.

## Outputs

```text
scripts/phase11_segment_fabric.py
results/segment_fabric/segment_forest_canonical_slots_v0.csv
results/segment_fabric/sspp_tool_slack_pipeline_v0.csv
results/segment_fabric/action_conditioned_backend_stub_v0.csv
results/segment_fabric/phase11_segment_lifecycle_fabric_summary_v0.csv
docs/phase11a_segment_forest_canonical_slots_report.md
docs/phase11b_sspp_tool_slack_pipeline_report.md
docs/phase11c_action_conditioned_backend_stub_report.md
```

## Main Findings

Phase 11A:

```text
mean_prefill_tokens_saved = 8831.879
mean_canonical_segment_cache_hit_rate = 0.955
```

This is the strongest new mechanism. It targets low-load repeated context and middle-insertion prefix miss, where Phase 10 RAR-exact had no goodput win.

Phase 11B:

```text
mean_hidden_fraction at prediction_hit_rate=1.0 = 0.789
50 ms slack hides 128/256/512 MB prefetch and small preparation actions
100 ms slack hides all tested actions
```

This gives ContractKV a normal agent-pipeline acceleration story: move segment preparation out of next-turn TTFT.

Phase 11C:

```text
uniform-int4: 140/140 quality-budget violations
contractkv-int4: 0/140 quality-budget violations
contractkv-int4 mean memory saving = 25.802 MB
contractkv-offload mean memory saving = 141.310 MB with 0 residual stall under 100 ms slack
```

This is not a backend performance claim. It shows the deciding layer: ContractKV uses the same primitive selectively and fail-closed.

## What Phase 11 Proves

```text
ContractKV should be positioned as a Segment-Contracted KV Lifecycle Fabric, not only RAR.
Different regimes need different actions.
Segment Forest targets prefix-miss / prefill work.
SSPP targets tool-slack critical-path hiding.
RAR targets block pressure and recompute work.
Quant/offload backends should be action-conditioned, not uniform.
```

## What Phase 11 Does Not Prove

```text
real vLLM prefix-cache hit improvement
real position-corrected non-linear KV grafting
real KIVI / LMCache / Tutti integration
real mixed-precision attention correctness
production goodput improvement
```

## Decision for Phase 12

The best next hard-system experiment is not arbitrary grafting yet.

Recommended Phase 12:

```text
Run real vLLM prefix-cache A/B:
  raw-order prompt with middle ToolObs insertion
  canonical-slot prompt
Measure:
  TTFT mean / p95
  prompt_tokens / cached-prefix observability if available
  output quality sanity
  SLO-compliant req/s under low and moderate load
```

If Phase 12 confirms real TTFT reduction, ContractKV has a clearer all-regime story:

```text
Segment Forest for low-load prefix miss
SSPP for tool-call slack
RAR for pressure rescue
action-conditioned backend selection for memory-constrained regimes
```
