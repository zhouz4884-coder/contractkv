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

## Phase 12E Update

Phase 12E explains why static POSC can still be slower than a coarse boolean guard:

```text
static POSC optimizes the current prompt DAG,
but boolean-guarded may accidentally preserve a de facto cached prefix from the previous turn.
```

The fix is Cache-Aware POSC (CAPOSC):

```text
POSC:
  semantic partial-order safety constraint

CAPOSC:
  state-aware candidate selector over raw / boolean / POSC / cache-preserving layouts
```

Phase 12E added:

```text
scripts/phase12e_cache_aware_posc.py
scripts/phase12e_multiturn_trajectory_builder.py
scripts/phase12e_multiturn_replay.py
docs/phase12e_cache_aware_posc_report.md
results/prefix_cache/phase12e_multiturn_replay_summary_v0.csv
results/prefix_cache/phase12e_multiturn_case_summary_v0.csv
```

The 36-turn, 180-record ledger-model replay shows:

```text
boolean-guarded:
  mean LCP = 247.056 tokens
  mean TTFT = 81.510 ms
  p95 TTFT = 156.808 ms

CAPOSC:
  mean LCP = 342.333 tokens
  mean TTFT = 70.186 ms
  p95 TTFT = 116.198 ms
```

Quality sanity stays at:

```text
1.000000 for all evaluated policies
```

This is not yet a real vLLM cached-token measurement. It is a deterministic segment-ledger replay that validates the compiler objective and produces the exact workload for the next real vLLM A/B.

The next step is:

```text
Phase 12F: real vLLM CAPOSC replay
  use the same multi-turn trajectories
  compare boolean-guarded / static POSC / CAPOSC
  measure real TTFT, TPOT, request latency, and any observable prefix-cache stats
```

## Phase 12F Update

Phase 12F ran the same 36-turn CAPOSC workload on real vLLM/Qwen3-8B with prefix cache enabled:

```text
180 real streamed policy requests
36 oracle-best-layout analysis rows
error_type none = 180 / 180
quality_bad = 0 / 180
```

At SLO = 300 ms:

```text
boolean-guarded:
  mean TTFT = 49.602 ms
  p95 TTFT = 91.970 ms
  SLO req/s = 3.431

CAPOSC:
  mean TTFT = 49.947 ms
  p95 TTFT = 76.871 ms
  SLO req/s = 3.427

CAPOSC + rebase:
  mean TTFT = 42.278 ms
  p95 TTFT = 48.697 ms
  SLO req/s = 3.524

oracle-best-layout:
  mean TTFT = 41.137 ms
  p95 TTFT = 46.890 ms
  SLO req/s = 3.538
```

This means:

```text
CAPOSC reduces p95 TTFT by 16.4% versus boolean-guarded.
CAPOSC + rebase reduces mean TTFT by 14.8% and p95 TTFT by 47.1% versus boolean-guarded.
CAPOSC + rebase is within 1.141 ms mean TTFT and 1.807 ms p95 TTFT of oracle-best-layout.
```

vLLM still did not expose cached-token usage through the tested OpenAI stream path:

```text
cached_tokens_observable_rate = 0.0
```

But real timing provides indirect calibration:

```text
estimated_new_prefill_tokens vs real_TTFT:
  workload Pearson r = 0.390593
  workload Spearman r = 0.402107
```

Phase 12F closes the key Phase 12E gap:

```text
CAPOSC is no longer only a ledger-model compiler objective.
It produces real vLLM tail-latency improvement while preserving marker/order quality sanity.
```

The next missing step is concurrent replay:

```text
Phase 12G:
  concurrency = 1 / 2 / 4
  evaluate SLO-compliant req/s under queue pressure
```

## Phase 12G Update

Phase 12G ran real vLLM concurrent replay with an unrecorded warmup pass:

```text
concurrency = 1 / 2 / 4
432 deployed-policy requests
108 oracle-best analysis rows
error_type none = 432 / 432
quality_bad = 0 / 432
```

At SLO = 300 ms:

```text
concurrency 1:
  boolean SLO req/s = 3.510
  CAPOSC + rebase SLO req/s = 3.516
  CAPOSC + rebase p95 TTFT = 48.283 ms

concurrency 2:
  boolean SLO req/s = 6.785
  CAPOSC + rebase SLO req/s = 6.826
  CAPOSC + rebase p95 TTFT = 51.285 ms

concurrency 4:
  boolean SLO req/s = 4.445
  CAPOSC SLO req/s = 4.864
  CAPOSC + rebase SLO req/s = 4.849
```

At concurrency 4, p95 TTFT is scheduler-dominated because client concurrency exceeds `max_num_seqs=2`:

```text
boolean p95 = 319.221 ms
CAPOSC p95 = 320.962 ms
CAPOSC + rebase p95 = 325.132 ms
```

So the concurrency result is not "CAPOSC always lowers p95." The correct claim is:

```text
CAPOSC + rebase is best or near-oracle at concurrency 1/2.
Under queue pressure, CAPOSC improves SLO-compliant req/s while p95 is dominated by scheduler saturation.
```

This closes Phase 12's serving story:

```text
single-stream:
  CAPOSC reduces real p95 TTFT.

concurrent replay:
  CAPOSC remains quality-safe and improves SLO-compliant req/s under queue pressure.
```

## Phase 13A Overhead And Rebase Accounting Note

Phase 13A measured CAPOSC compiler overhead on the same 36-turn trace with 1000 repeats:

```text
num compiles = 36000
compile mean = 0.388654 ms
compile p95 = 0.818500 ms
ledger lookup mean = 0.248554 ms
candidate eval mean = 0.159045 ms
candidate count = 5
```

Relative to Phase 12F real CAPOSC+rebase timing:

```text
compiler mean / mean TTFT = 0.92%
compiler p95 / p95 TTFT = 1.68%
```

This supports:

```text
CAPOSC compiler overhead is sub-millisecond and small relative to TTFT.
```

However, Phase 13A also found:

```text
rebase_triggered_count = 0 / 36000
rebase_hidden_by_slack_count = 0 / 36000
```

So the Phase 12F/12G `CAPOSC + rebase` label should not be described as proof that an explicit rebase actuator fired on this workload. The safe wording is:

```text
CAPOSC rebase accounting is implemented, but the current heuristic did not trigger on the Phase 12 trace.
Rebase needs a separate stress workload before being claimed as an active mechanism.
```
