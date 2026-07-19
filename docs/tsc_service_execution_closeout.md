# TSC Service Evaluation Execution Closeout

## Status

The full-strength service extension completed on two RTX 3090 GPUs and passed
the machine-readable gate in
`results/tsc_service/tsc_service_extension_gate_v0.json`.

The live serving matrix contains 66 natural open-loop cells, 129 authorized
service-locality cells, 3 certificate-granularity ablation cells, 36
locality-residency cells, and 102 multi-tenant cells. The original matrix issued
288,495 future requests. The closure adds 2,700 task-bearing quality requests
and reuses the identical 1,125-request trace for the three D2-session repeats.
The extension also ran 24 verification-economics model points and 10
service-lifecycle events.

## Headline Results

- Qwen3-8B, 25 tenants per authorized template, 80% load: ContractKV reduced
  mean TTFT by 92.62%, p99 TTFT by 95.78%, and new-prefill work by 98.15%; the
  500-ms SLO-goodput multiplier was 4.81x.
- Mistral-7B, the same 25-tenant scope and 80% load: mean TTFT fell by 54.35%,
  new-prefill work by 50.75%, and 500-ms SLO goodput improved by 4.48x.
- Hierarchical resampling gives Qwen mean-TTFT reduction 92.62% with 95% CI
  [91.68%, 93.31%], p99 reduction 95.70%-95.83%, and a 500-ms absolute
  SLO-goodput gain of 0.658 req/s [0.539, 0.765]. The corresponding finite
  multiplier is 4.81x [2.85x, 12.61x].
- Mistral mean-TTFT reduction is 54.37% [34.25%, 72.02%], with a 500-ms
  absolute SLO-goodput gain of 0.340 req/s [0.129, 0.538]. Its 4.48x point
  multiplier is retained, but the clustered ratio CI is not identifiable
  because some resamples contain zero native requests under the tight SLO.
- At 40 tenants with fully authorized sharing, steady SLO goodput rose from
  1.064 to 10.984 requests/s while mean TTFT fell from 1364.5 to 90.8 ms.
- At 80-tenant density, ContractKV used 149 peak KV blocks versus 530 for raw
  vLLM, retained 2237 free blocks versus 1856, and delivered 11.033 versus
  1.152 SLO-compliant requests/s.
- Across the residency sweep, Zipf locality retained a 73.40% mean-TTFT
  reduction even with 50 active templates. Round-robin reuse at 25 and 50
  templates exposed the expected cache-residency boundary.

## Safety and Economics

Unauthorized cross-tenant reuse, dynamic-suffix reuse, and scope-invalid
admissions were all zero. All 10 lifecycle mutations invalidated old
certificates and prevented old-prefix consumption without disrupting unrelated
scopes.

The live economics sweep had 71 positive lanes out of 84. Certificates were
accepted for 82 lanes. Two rejected Mistral lanes executed measured raw-order
fallback; a rejected certificate is not reported as a compiled-policy success.
This remains an operating-region analysis, not a claim that the current
benefit predictor perfectly rejects every negative lane.

## P0-A Task Quality

Five real task-bearing templates each serve ten tenants for ten turns under
three paired fresh processes. D0 and the guarded D2 policy each complete all
1,350 future outputs. Frozen RULER, LongBench, and RepoBench task scores are
identical overall (0.356 versus 0.356), with zero policy-attributable quality
violations, scope-invalid admissions, unauthorized reuse, or dynamic-suffix
reuse. RULER, HotpotQA, NarrativeQA, and RepoBench receive shared template
certificates; Qasper follows the pre-existing fail-closed raw fallback.

The archived all-template negative control produced three lexical F1 drops,
all from the same Qasper turn. Both compared answers were incorrect against
the reference; more importantly, the unguarded policy violated the already
known Qasper scope. The paper-facing guarded policy eliminates all three drops
by declining publication rather than by changing the quality threshold.

## P0-B Certificate Granularity

At identical 25-tenant locality and 80% load, D2-session and D2-template have
nearly identical serving work: 50.2 versus 41.7 new-prefill tokens, a difference
of 8.5 tokens or 0.37% of the prompt. Template scope reduces verifier calls
from 125 to 5 (25x), raises fan-out from 9 to 225 requests per certificate, and
reduces unhidden verification cost from 25.049 to 3.236 ms/request (7.74x).
Completion, quality sanity, and isolation remain unchanged.

## Negative Control

The natural mixed-session trace has effectively unique stable content. In that
scope ContractKV reduced neither prefix work nor TTFT and paid 1.6%-8.7%
overhead, depending on model and load. This is a useful boundary result: the
service-template mechanism should be enabled only when the prospective scope
and benefit gate identify authorized reuse.

## Implementation Corrections

Two issues found during execution were code or evaluation-logic defects, not
failures of the service-locality hypothesis:

1. A Bash `set -u` failure expanded `tag` before its same-line local assignment
   in the residency and multi-tenant runners. Splitting assignment and use
   fixed the orchestration; a regression test now covers it.
2. The first economics gate incorrectly required every boundary point to issue
   a certificate, and rejected points still executed the compiled candidate.
   The final implementation requires transaction-consistent outcomes and
   executes real raw-order fallback after a rejection. The economics sweep was
   rerun before the final gate was generated.

## Claim Boundary

TTFT, SLO goodput, prefix work, block-pool occupancy, lifecycle, and isolation
results are from real vLLM serving. Marker sanity validates request-path
behavior but is not substituted for official RULER, LongBench, or RepoBench
scoring. P0-A uses frozen task metrics and task-specific output budgets, but is
a five-template deployment-object audit rather than a full benchmark run. The
former zero-denominator capacity table and extreme 200%-800% goodput ratios are
not headline evidence; the main-text curve is limited to 60%-140% load. Exact
vLLM prefix-cache eviction counts were unavailable and were not fabricated;
the residency analysis uses observed prefix-hit work, reuse distance,
zero-hit-after-prior-template events, and physical block counters.
