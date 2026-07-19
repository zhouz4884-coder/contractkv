# ContractKV TSC Service Model and Frozen Protocol

## Service model

A service template is a versioned stable prompt state comprising the system
prompt, tool schema, and approved knowledge or repository context. A tenant is
an independently identified principal with a private observation stream, a
service-class SLO, and an explicit sharing scope. A session is a ten-turn use of
one template by one tenant. Only a certified stable prefix may be reused;
private observations and user queries remain outside the authorized shared
scope.

The cache sharing key contains the model identity, tokenizer/chat-template
identity, service-template version, stable-content hash, policy hash,
qualification hash, and tenant authorization scope. Identical text with a
different scope or policy hash is deliberately salted to a different token
prefix. This makes forbidden sharing a property of the real vLLM cache key,
not a post-hoc accounting label.

Certificate use has four distinct stages. Prospective offline qualification
authorizes a model/workflow/layout route. Deployment attestation verifies and
transactionally publishes one immutable service-template version. Each future
request performs only a hash-and-scope lookup over model, tokenizer/chat
template, template version, stable content, layout, policy, qualification,
authorization domain, and epoch. Dynamic queries, tool observations, and
tenant-private suffixes are excluded from the published scope.

## Frozen workload

The service trace is selected deterministically from the disjoint
`phase14/live_serving` partition:

- five families: RULER, HotpotQA, NarrativeQA, Qasper, and RepoBench;
- 25 source-group-disjoint sessions per family;
- 125 sessions and ten turns per session;
- one unmeasured registration turn and 1,125 future requests per cell;
- one frozen unit-rate exponential arrival trace, scaled only by the
  pre-registered load fraction;
- identical sessions, turn order, and arrival gaps for D0, D1, and D2.

The trace hashes are recorded in
`results/tsc_service/tsc_service_trace_commitment_v0.json`. Partial cells are
discarded rather than resumed.

The natural mixed trace intentionally has one distinct stable context per
session and is retained as a low-locality boundary. A separately committed
service-locality family uses 1, 5, or 25 tenants per authorized stable service
template while preserving tenant-private observations, requests, and the same
arrival trace. This sweep tests when service-template reuse is physically
available; it does not replace or hide the natural mixed result.

A second frozen residency sweep holds 1,125 requests and the exponential gap
multiset fixed while varying 5, 25, or 50 active templates under round-robin
and Zipf arrival order. vLLM 0.10.2 does not expose an exact scheduler-level
prefix-cache eviction counter in this probe. The reports therefore retain the
counter as unavailable and use zero prefix hits after a prior template visit
only as an explicitly named residency-miss signal.

## Policies

- **D0 Native vLLM APC:** raw prompt order and native automatic prefix cache.
- **D1 Frozen-safe layout:** the prospectively qualified family layout with no
  live registration or verification.
- **D2 Full ContractKV:** same frozen family policy plus real same-backend
  compact verification and transactional certificate registration. Failed or
  ineligible sessions fall back to raw order.

The certificate fan-out ablation additionally retains **D2-Session**, which
pays the same safety mechanism once per session, and **D2-Template**, which
pays once per deployed template and performs a per-request scope lookup. This
isolates certificate-object granularity without changing the compiled layout.

The D1/D2 split attributes layout benefit separately from online verification
cost. D2 reports registration time, verification time, and the part not hidden
by the declared tool slack.

The service-scaling cells cap generation at 64 tokens because they use a short,
deterministic response marker to isolate TTFT, queueing, and prefix reuse. This
is not a proposed production response limit. Long-output task quality remains
covered by the earlier fresh-generation benchmark scoring, and marker sanity is
reported only as a request-path correctness check.

## Capacity and SLO

Capacity and SLO compliance are deliberately distinct. The pilot freezes the
highest offered rate with at least 99% completion, zero timeout/drop, and a
non-growing scheduler queue (`wait slope <= 0.02 s/s`). The full matrix then
reports independent 500, 1,000, 1,500, and 3,000 ms primary SLO curves at 60%,
80%, 100%, and 120% of that capacity; 750 ms is retained as a cost-free
auxiliary sensitivity point. A system may therefore remain
queue-stable while violating a tight SLO; the evaluation does not conflate the
two.

## Multi-tenant authorization

The full-strength design includes 10-tenant qualification cells, 20-tenant
intermediate cells, a 40-tenant 0/25/50/75/100% sharing curve, and a
10/20/30/40/60/80-tenant density sweep. Every tenant has private observations and
queries. Different service versions, models, policy hashes, qualification
hashes, or revoked tenant epochs cannot share. The required safety gates are:

- unauthorized cross-tenant reuse = 0;
- scope-invalid admission = 0;
- dynamic-suffix reuse = 0;
- shared physical-block refcount match = 100%;
- policy-attributable quality violations = 0.

Gold, Silver, and Bronze service classes use 750, 1,500, and 3,000 ms TTFT
SLOs. ContractKV is not presented as a priority scheduler; the experiment asks
whether prefix optimization preserves tenant-level fairness.

## Verification economics

The deployment operating region uses

```text
break_even_reuses = ceil(max(verification + promotion - tool_slack, 0)
                          / saved_time_per_future_turn)
```

for stable prefixes of 1K, 2K, 4K, and 6K tokens and future horizons of 2, 5,
10, and 20 turns. Twelve boundary points run real same-backend registration and
future requests on Qwen3-8B and Mistral-7B. The remaining contour cells
interpolate only measured per-turn savings and measured registration costs and
remain labeled analytical.

## Claim boundaries

Open-loop latency, queue, cache, physical-block, and completion metrics are
real vLLM observations. Marker checks validate request behavior but are not
substituted for official benchmark scoring; official task-quality evidence is
reported separately. Model-checkpoint and tokenizer lifecycle events validate
certificate routing and invalidation scope without claiming in-process weight
replacement.
