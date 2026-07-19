# TSC Service Evaluation Execution Closeout

## Status

The full-strength service extension completed on two RTX 3090 GPUs and passed
the machine-readable gate in
`results/tsc_service/tsc_service_extension_gate_v0.json`.

The live serving matrix contains 66 natural open-loop cells, 129 authorized
service-locality cells, 36 locality-residency cells, and 102 multi-tenant
cells. These cells issued 288,495 future requests. The extension also ran 24
verification-economics model points and 10 service-lifecycle events.

## Headline Results

- Qwen3-8B, 25 tenants per authorized template, 80% load: ContractKV reduced
  mean TTFT by 92.62%, p99 TTFT by 95.78%, and new-prefill work by 98.15%; the
  500-ms SLO-goodput multiplier was 4.81x.
- Mistral-7B, the same 25-tenant scope and 80% load: mean TTFT fell by 54.35%,
  new-prefill work by 50.75%, and 500-ms SLO goodput improved by 4.48x.
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
scoring. Exact vLLM prefix-cache eviction counts were unavailable and were not
fabricated; the residency analysis uses observed prefix-hit work, reuse
distance, zero-hit-after-prior-template events, and physical block counters.
