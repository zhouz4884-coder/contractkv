# Phase 12 Prefix-Cache Closeout

## What Phase 12 Added

Phase 12 moves ContractKV's Segment Forest idea from an offline estimate to real vLLM serving.

The core comparison was:

```text
raw-order + prefix cache
canonical-slot + prefix cache
cold raw-order with prefix cache disabled
```

## Main Result

Canonical-slot layout achieved strong success:

```text
raw-order mean TTFT = 638.457 ms
canonical-slot mean TTFT = 58.590 ms
mean TTFT reduction = 90.823%

raw-order p95 TTFT = 640.707 ms
canonical-slot p95 TTFT = 64.610 ms
p95 TTFT reduction = 89.916%
```

Quality sanity:

```text
raw-order = 5/5
canonical-slot = 5/5
cold-raw = 5/5
```

## What This Proves

This closes the biggest gap left by Phase 10.5:

```text
RAR-exact is a hard actuator but only helps under block/recompute pressure.
Canonical-slot Segment Forest can help even in low-load repeated-context workflows.
```

ContractKV now has a multi-regime systems story:

```text
low / normal load:
  Segment Forest canonical slots reduce prefill TTFT.

tool-call gap:
  SSPP moves segment preparation into slack.

KV pressure:
  RAR-exact releases suffix blocks and saves recompute tokens.

memory constrained:
  action-conditioned backend selection can use quant/offload fail-closed.
```

## What This Does Not Prove

Phase 12 still does not claim:

```text
arbitrary segment KV grafting
RoPE-corrected non-linear stitching
real KIVI / LMCache integration
cached-token count improvement, because vLLM did not expose cached-token usage through the tested OpenAI stream path
production SLO goodput improvement
```

## Decision

Phase 12A is a strong positive result.

Recommended next step:

```text
Phase 12B: concurrent canonical-slot replay
Phase 12C: real LongBench / RepoBench prompt layout quality check
```

The paper narrative should now lead with:

```text
ContractKV is a segment lifecycle fabric.
RAR is one actuator, not the whole system.
Canonical slots provide the first clear low-load serving benefit.
```
