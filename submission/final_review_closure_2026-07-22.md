# ContractKV TSC Final Review Closure

## Scope

This closure reconciles the 2026-07-22 external review against the 12-page
submission artifact. It changes presentation and protocol descriptions only;
it does not rerun experiments or alter measured result files.

## Blocking Consistency Fixes

- The frozen net-benefit gate is reported as accepting 2/4 sealed lanes, with
  both accepted lanes net-positive. Non-admitted lanes execute raw order;
  diagnostic rejected outcomes are not treated as classifier labels.
- D0/D1/D2 now have one paper-wide definition: native raw APC; frozen safe
  layout without online verification or certificate publication; and full
  template-scoped ContractKV with in-engine verifier registration,
  certificate publication, and request-scope checking.
- Protocol counts distinguish requests per repeat from total requests per cell.
  Llama and same-engine comparisons use 450 requests per repeat and 2,250 per
  complete five-process cell; the task-bearing template audit uses 1,350 paired
  outputs over three processes.
- The service manifest is denoted by `mathcal M`, avoiding collision with model
  configuration `M`. Scope checks bind the complete composite identity,
  including generation configuration and runtime fingerprint.

## Certification Semantics

- Certified serving paths use deterministic greedy decoding at temperature 0
  with sampling disabled.
- Generation configuration, stop protocol, output budget, model/runtime,
  tokenizer/template, policy, authorization domain, and lifecycle are bound.
- Route qualification, immutable template registration, and per-request scope
  authorization are described as separate evidence layers.
- A service-template certificate is explicitly an empirical authorization for
  a prospectively qualified immutable route, not a per-query equivalence proof.
- The 0.03 material-effect threshold is a development-frozen reporting gate,
  not an equivalence tolerance used to admit a request.

## Baseline and Novelty Boundaries

- Llama direct comparisons are matched-runtime deltas. ContractKV and
  CacheBlend reduce mean TTFT by 29.16% and 26.96% against their own runtimes;
  their absolute means are descriptive and not used as a cross-runtime causal
  comparison.
- Runtime controls record native prompt serialization, LMCache 0.3.9,
  FlashInfer 0.3.1, CUDA 12.8, the three compatibility changes, and the
  CacheSlide concurrency/equivalence blocker.
- Related work now includes CacheSlide, EPIC, MiniPIC, and Parrot and positions
  ContractKV around evidence, identity, authorization, lifecycle, and atomic
  publication rather than claiming a new cross-position KV primitive.

## Retained Headline Evidence

- Four configurations remain globally net-positive: 29.41%-44.69% lower mean
  TTFT and 1.19x-2.92x SLO-goodput, including frozen L0 and residual verifier
  exposure.
- An identical frozen RULER scope converges to 85.97%-87.41% TTFT reduction
  across Qwen, Mistral, and Llama.
- The primary Qwen3-8B service point delivers 92.62% lower mean TTFT, 4.81x
  500-ms SLO-goodput, and 72% lower peak used KV blocks.
- Llama reports 0/1,125 admitted compiled regressions, with a one-sided exact
  95% upper bound of 0.266%; both overall events are raw fallback and reproduce
  under raw-only control.
- Same-engine D2 preserves D1's 935.86-ms p99 while charging verifier
  registration wall time; service-template scope reduces unhidden verification
  exposure by 7.7x at fixed layout and locality.

## Figure and PDF QA

- Figure 1 was left unchanged.
- Figures 2-6 were regenerated from `submission/gen_tsc_figures_v5.py` and
  inspected both individually and in the final single-column PDF placement.
- Figure 2 prints qualification level and measured coverage in every cell.
- Figure 3 emphasizes matched-runtime performance and admitted-path risk.
- Figure 4 reports absolute D0/D1/D2 goodput before the 21.5x multiplier and
  distinguishes layout-only D1 from in-engine certified D2.
- Figure 6 reports the locality knee, residency behavior, and the frozen 2/4
  admission outcome without relabeling rejected diagnostics.
- Final PDF: 12 pages, no undefined citations or references, no overfull boxes,
  and no visible clipping or overlap in the rendered page audit.

## Claim Boundary

The paper establishes governed reuse within one vLLM cache domain. It does not
claim production-cluster scalability, arbitrary-query equivalence, a direct
cross-runtime CacheBlend speed win, or that KV-block reduction is identical to
provider cost reduction.
