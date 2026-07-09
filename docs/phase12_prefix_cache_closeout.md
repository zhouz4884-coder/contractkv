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

## Phase 12B/12C Update

Phase 12B extended the result to concurrent replay with mixed RULER, LongBench, and RepoBench contexts.

At SLO = 700 ms:

```text
concurrency 1:
  raw-order SLO req/s = 0.958
  canonical-slot SLO req/s = 3.547

concurrency 2:
  raw-order SLO req/s = 1.025
  canonical-slot SLO req/s = 6.325

concurrency 4:
  raw-order SLO req/s = 0.466
  canonical-slot SLO req/s = 6.639

concurrency 6:
  raw-order SLO req/s = 0.348
  canonical-slot SLO req/s = 6.846
```

Phase 12C checked real-task quality sanity. RULER and the tested LongBench subset stayed within the <= 0.03 quality-drop threshold, but RepoBench showed a large drop:

```text
RULER niah_single_1 drop = 0.000000
LongBench hotpotqa drop = 0.000000
LongBench qasper drop = 0.015670
LongBench narrativeqa drop = 0.000000
RepoBench python_repository_completion drop = 0.333333
```

This adds a layout guard:

```text
canonicalize only when the segment contract allows reordering;
otherwise preserve raw order.
```

## Decision

Phase 12A and Phase 12B are strong positive serving results.

Phase 12C shows canonical-slot is safe for the tested RULER/LongBench cases but not universally safe for RepoBench code completion.

Recommended next step:

```text
Phase 13: larger POSC compiler evaluation
  extend POSC from 30 mixed-agent sanity cases to larger real agent traces
  learn/select when structural anchors are worth their token overhead
  report coverage, violated_edges, SLO req/s, and real task quality
```

## Phase 12D Update

Phase 12D implemented the guarded compiler as a Partial-Order Segment Contract system rather than a boolean task guard.

The key real vLLM mixed-agent result:

```text
canonical-all:
  quality score = 0.666667
  violated edge cases = 10

boolean-guarded:
  quality score = 1.000000
  canonicalized fraction = 0.333333

POSC:
  quality score = 1.000000
  canonicalized fraction = 1.000000
  violated edge cases = 0

POSC + anchors:
  quality score = 1.000000
  canonicalized fraction = 1.000000
  violated edge cases = 0
```

This is the clean Phase 12 conclusion:

```text
canonical-slot is useful, but only as a compiler output.
The compiler must preserve semantic partial orders.
POSC is stronger than if-else layout guards because it enables partial-canonical layouts.
```

The paper narrative should now lead with:

```text
ContractKV is a segment lifecycle fabric.
RAR is one actuator, not the whole system.
Canonical slots provide the first clear low-load serving benefit.
```
