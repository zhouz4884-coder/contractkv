# ContractKV Fig. 2--Fig. 6 Data and Story Specification

## Purpose and Freeze Rules

This document freezes the data, statistical meaning, and intended conclusion
for the five single-column evaluation figures in `contractkv_tsc.tex`. It is the
source of truth for later Python, Visio, or manual redrawing.

The figures must form one evidence chain:

1. **Fig. 2:** the mechanism generalizes and remains net-positive globally;
2. **Fig. 3:** on a common Llama platform, ContractKV has the best measured
   performance--behavior trade-off, and its tail is explained by deliberate raw
   fallback rather than unsafe compiled requests;
3. **Fig. 4:** the full verifier is in the same serving path, while template
   certificates reduce verification economics without manufacturing cache hits;
4. **Fig. 5:** the mechanism becomes real open-loop SLO goodput and physical KV
   block headroom at service scale;
5. **Fig. 6:** benefit appears only in a measurable locality/residency region,
   and a frozen gate safely keeps unprofitable scopes on raw order.

General rules:

- ContractKV uses one saturated blue or teal; native/raw uses neutral gray.
- Orange denotes an unsafe or approximate comparison, not ContractKV failure.
- Red is reserved for a violated threshold or abort.
- Every panel must state whether it is real serving, a cross-runtime diagnostic,
  or deterministic protocol stress.
- p95/p99 are pooled request-level quantiles unless explicitly labeled as a
  repeat range or cluster-bootstrap interval.
- Do not use the 659x--3158x overload ratios or an "unbounded capacity" claim.
- Do not infer HBM saving from new-prefill tokens. Only allocator-observed
  physical block counts support the memory/deduplication claim.
- Do not call the SGLang frozen-layout cell full online ContractKV: it consumes
  an offline certified layout but does not run PSTP or issue certificates.
- Do not assign a performance number to CacheSlide: its supplied artifact fails
  the frozen concurrency-2 isolation/output-equivalence protocol.

---

## Fig. 2 - Global Benefit and Frozen Qualification

### Core question

**Does ContractKV remain useful beyond one model, after charging fallback and
verification rather than showing only successful compiled requests?**

### Recommended composition

A 2x2 small-multiple figure:

- (a) all-workflow net mean TTFT reduction;
- (b) all-workflow new-prefill reduction;
- (c) all-workflow net SLO-goodput multiplier;
- (d) frozen model--workflow qualification map.

### Panel (a): net mean TTFT reduction

| Model configuration | Reduction |
|---|---:|
| Qwen3-8B | 37.81% |
| Qwen3-14B, TP=2 | 44.69% |
| Mistral-7B-Instruct-v0.3 | 31.72% |
| Llama-3.1-8B-Instruct | 29.41% |

Meaning: three fresh-process repetitions; all five workflows; prospectively
frozen L0 families, runtime fallback, and residual verification exposure are
included. These are not qualified-subset-only numbers.

Primary conclusion: **all four configurations remain net-positive, and the
larger Qwen3-14B TP=2 point strengthens rather than erases the benefit.**

### Panel (b): new-prefill work reduction

| Model configuration | Reduction |
|---|---:|
| Qwen3-8B | 59.13% |
| Qwen3-14B, TP=2 | 60.57% |
| Mistral-7B | 39.46% |
| Llama-3.1-8B | 30.97% |

Meaning: scheduler/token-work evidence. It directly measures avoided prompt
prefill work, not memory saving.

Primary conclusion: **ContractKV removes 31--61% of redundant prompt work;
the smaller net TTFT reduction is expected because serving and verification
costs are already charged.**

### Panel (c): net SLO-goodput multiplier

| Model configuration | Multiplier |
|---|---:|
| Qwen3-8B | 2.64x |
| Qwen3-14B, TP=2 | 2.92x |
| Mistral-7B | 1.24x |
| Llama-3.1-8B | 1.19x |

The horizontal baseline is `native = 1.0x`. Each raw/ContractKV pair uses its
pre-frozen model--workflow SLO; this panel is not a cross-model absolute-rate
comparison.

Primary conclusion: **the reduction in prefill work produces positive SLO
goodput for every model, not merely lower isolated TTFT.**

### Panel (d): frozen qualification map

Each cell should show frozen level and compiled coverage. L3* means a full
compiled candidate without separately calibrated L1/L2 semantics.

| Model / family | RULER | HotpotQA | NarrativeQA | Qasper | RepoBench |
|---|---:|---:|---:|---:|---:|
| Qwen3-8B | L3* / 100% | L3* / 70% | L3* / 50% | L3* / 70% | L3* / 50% |
| Mistral-7B | L3* / 100% | L3* / 70% | L3* / 60% | L3* / 10% | L3* / 10% |
| Llama-3.1-8B | L3 / 100% | L2 / 90% | L2 / 60% | L0 / 0% | L0 / 0% |

Global certificate coverage is 68%, 68%, 50%, and 50% for Qwen3-8B,
Qwen3-14B, Mistral, and Llama, respectively. The Qwen3-14B row need not be
drawn in the family map unless its family-level table is shown separately.

Primary conclusion: **coverage differences are evidence that certification is
needed; ContractKV does not force one aggressive layout on every model.**

### Optional compact callout (not another panel)

Identical frozen RULER scope, 30 sessions x 10 turns x three process pairs:

| Model | Net TTFT reduction | 95% CI | New-prefill reduction |
|---|---:|---:|---:|
| Qwen3-8B | 86.64% | [86.16%, 87.10%] | 96.71% |
| Mistral-7B | 87.41% | [87.06%, 87.79%] | 95.86% |
| Llama-3.1-8B | 85.97% | [85.63%, 86.29%] | 95.45% |

Macro reduction is 86.67% [86.44%, 86.90%]; the model range is 1.44
percentage points. Use this only as a caption callout if Fig. 2 remains legible.

### Evidence sources

- `results/submission_repeats/submission_repeat_aggregate_v0.csv`
- `results/scale_up/qwen3_14b_tp2_v0/aggregate_summary_v0.csv`
- `results/cross_model/llama_broad_generalization_r3/heldout_scope_aggregate_v0.csv`
- `results/submission_supplement/common_ruler_qwen_aggregate_v0.csv`
- `results/submission_supplement/common_ruler_mistral_aggregate_v0.csv`
- `docs/common_ruler_cross_model_report.md`
- `submission/claim_evidence_matrix.md`

### Claims to avoid

- Do not say four model families; these are four configurations from three
  families.
- Do not say every request is compiled. L0 and runtime fallback are included.
- Do not average the goodput multipliers across models.
- Do not call one TP=2 point a cluster scalability law.

---

## Fig. 3 - Llama Direct Baselines and Tail Attribution

### Core question

**Against available non-prefix-reuse systems on a common Llama platform, does
ContractKV trade task behavior for speed, and where does its tail come from?**

### Recommended composition

Two vertically stacked panels:

- (a) performance--behavior frontier;
- (b) request-class mean/p95/p99 tail decomposition.

### Panel (a): performance--behavior frontier

Use x = matched-runtime mean TTFT reduction and y = observed paired task-score
regression rate above 0.03 on a logarithmic scale.

| Method | Matched baseline | Mean TTFT (ms) | Reduction | Regression >0.03 |
|---|---|---:|---:|---:|
| ContractKV | vLLM APC raw order | 722.92 | 29.16% | 0.089% overall; 0/1,125 admitted compiled |
| CacheBlend | LMCache separator baseline | 739.04 | 26.96% | 9.956% |
| Manual stable-layout upper bound | vLLM APC raw order | 633.95 | 37.87% | 1.733% |
| SGLang + frozen certified layout | SGLang raw RadixAttention | 668.99 | 26.60% | 0.089% |

Underlying matched baselines:

| Baseline | Mean / p95 / p99 TTFT (ms) | SLO goodput | New-prefill |
|---|---:|---:|---:|
| vLLM APC raw | 1020.44 / 1705.57 / 2292.98 | 0.835 req/s | 2372.3 |
| SGLang raw | 911.45 / 1758.09 / 2351.44 | 0.844 req/s | unavailable |
| LMCache separator baseline | 1011.88 / 1738.03 / 2300.50 | 0.778 req/s | 2300.1 |
| LMCache local-CPU connector | 1078.92 / 1822.80 / 2416.42 | 0.797 req/s | 2471.5 |

All complete cells use five fresh processes and 450 future requests per repeat,
for 2,250 paired task-bearing requests where quality comparison is applicable.

Primary conclusion: **ContractKV slightly exceeds CacheBlend's matched-runtime
mean-TTFT reduction while reducing observed material regressions by more than
two orders of magnitude. The manual layout is faster but behaviorally unsafe.**

Important attribution: the two observed ContractKV-vs-raw drops are the same
runtime-fallback request; it had no verifier PASS, no certificate, and effective
L0. A cyclic raw-vs-raw control reproduces the phenomenon once (0.044%). Among
1,125 admitted compiled requests, material regressions are 0; the one-sided 95%
upper bound is approximately 0.266%.

Draw SGLang with a hollow marker and label it `portability diagnostic`, because
the layout is consumed by SGLang but certification/PSTP are not online there.

### Panel (b): request-level Llama tail attribution

| Request class | Share | Mean TTFT | p95 | p99 | Reduction vs paired raw | 1500-ms attainment |
|---|---:|---:|---:|---:|---:|---:|
| Admitted compiled | 50% | 263.29 | 699.50 | 898.96 | 68.30% | 100.0% |
| Manifest-direct L0 | 40% | 1261.76 | 1778.89 | 2311.01 | -0.33% | 71.1% |
| Runtime fallback | 10% | 865.68 | 1125.58 | 1129.17 | 15.20% descriptive | 100.0% |
| Overall mixture | 100% | 722.92 | 1716.74 | 2306.46 | 29.16% | 88.4% |

Draw a horizontal interval from mean to p99 with separate mean, p95, and p99
markers, plus a vertical 1500-ms SLO line.

Primary conclusion: **compiled requests have a sub-900-ms p99 and 100% SLO
attainment; the overall tail is dominated by deliberately retained L0 scopes,
not by the verifier corrupting compiled requests.**

### Evidence sources

- `results/tsc_closure/llama_sota_matrix_v1.csv`
- `results/tsc_closure/llama_tail_stratification_v1.csv`
- `docs/tsc_six_task_closure_report.md`
- `docs/llama_quality_tail_closure_report.md`

### Claims to avoid

- Do not compare absolute CacheBlend and ContractKV times as a same-stack causal
  result; compare each to its matched runtime.
- Do not claim SGLang runs online ContractKV.
- Do not report CacheSlide proxy performance.
- Do not say zero overall regressions; say 0/1,125 admitted compiled and 0.089%
  overall, with the fallback/control attribution.

---

## Fig. 4 - Same-Engine Verification and Certificate Economics

### Core question

**Does the full verifier really sit in the serving path, and does template scope
reduce verification cost rather than merely changing locality?**

### Recommended composition

Three panels:

- (a) same-engine D0/D1/D2 mean-to-p99 TTFT;
- (b) absolute 500-ms end-to-end SLO goodput;
- (c) same-locality session-vs-template certificate ablation.

### Policy definitions

- **D0 native APC:** raw-order, unmodified vLLM APC.
- **D1 frozen safe layout:** same frozen compiled layout, without online template
  certificate registration/amortization.
- **D2 full ContractKV:** same engine/endpoint, template registration through the
  live verifier path, signed binding, certificate lookup, and compiled serving.

### Panels (a) and (b): five-repeat same-engine closure

| Policy | Completion | Mean TTFT | p99 TTFT | 500-ms E2E goodput | Quality drop |
|---|---:|---:|---:|---:|---:|
| D0 native APC | 100% | 2742.83 ms | 7531.79 ms | 0.066 req/s | 0 |
| D1 frozen safe | 100% | 194.95 ms | 935.86 ms | 1.472 req/s | 0 |
| D2 full ContractKV | 100% | 194.72 ms | 935.86 ms | 1.428 req/s | 0 |

D2 performs four verifier endpoint calls and four template commits in each
fresh process, with zero registration failure. Registration wall time is charged.
D2 mean TTFT reduction versus D0 is 92.90%. The absolute 500-ms goodput gain is
1.362 req/s; the 21.49x ratio may appear in body text or caption, but absolute
rates should be visually primary because the D0 denominator is near zero.

Primary conclusion: **the in-engine verifier does not erase the layout benefit;
D1 and full D2 have essentially identical tails, while D2 closes the deployment
path with online registration and binding.**

### Panel (c): same-locality certificate granularity

Fixed 25 tenants/template, identical 1,125-request trace, 80% load, three fresh
processes, and the same safe layout:

| Metric | D2 session certificate | D2 template certificate |
|---|---:|---:|
| Verifier calls | 125 | 5 |
| Commits | 125 | 5 |
| Verification fan-out | 9 | 225 |
| Unhidden verification | 25.05 ms/request | 3.24 ms/request |
| Mean prompt tokens | 2300.19 | 2300.19 |
| Mean new-prefill tokens | 50.17 | 41.67 |
| Prefix-hit ratio | 97.82% | 98.19% |
| Mean TTFT | 64.02 ms | 62.91 ms |
| p99 TTFT | 89.51 ms | 88.02 ms |
| SLO goodput | 0.830648 req/s | 0.830651 req/s |
| Completion / quality sanity | 100% / 100% | 100% / 100% |
| Unauthorized or dynamic-suffix reuse | 0 / 0 | 0 / 0 |

Derived results: 25x fewer verifier calls; 7.7x less unhidden verification cost;
new-prefill differs by 8.5 tokens, only 0.37% of the prompt.

Primary conclusion: **certificate-object granularity changes safety economics,
not the underlying layout or prefix-locality opportunity.**

### Quality badge or caption evidence

Five real service templates x 10 tenants x 9 future turns x three process pairs:

- 1,350/1,350 paired outputs complete;
- raw and D2 mean task score are both 0.356;
- paired difference 0.0 and zero drop above 0.03;
- zero scope-invalid admission, unauthorized reuse, and dynamic suffix reuse;
- Qasper is prospectively unqualified and uses raw fallback.

This should be a compact caption/badge, not a fourth dense panel.

### Evidence sources

- `results/tsc_closure/real_task_open_loop_summary_v1.csv`
- `results/tsc_service/certificate_granularity_ablation_v0.csv`
- `results/tsc_service/service_template_quality_summary_v0.csv`
- `docs/pre_submission_experimental_closure_v1.md`
- `docs/tsc_six_task_closure_report.md`

---

## Fig. 5 - Open-Loop Goodput and Physical KV Deduplication

### Core question

**Does certified structural reuse produce service-level benefit under load and
reduce real physical block occupancy as tenant fan-out grows?**

### Recommended composition

Three panels:

- (a) 25-tenant open-loop 500-ms SLO goodput versus offered load;
- (b) SLO goodput versus tenant density;
- (c) allocator-observed peak used KV blocks at 80 tenants.

### Panel (a): open-loop load sweep

Qwen3-8B, 25 tenants/template, Poisson open-loop arrival, three fresh processes,
1,125 future requests per cell, template-scoped D2:

| Offered load | Native APC goodput | ContractKV goodput |
|---:|---:|---:|
| 60% | 0.1434 req/s | 0.6230 req/s |
| 80% | 0.1727 req/s | 0.8307 req/s |
| 100% | 0.1718 req/s | 1.0382 req/s |
| 120% | 0.1530 req/s | 1.2458 req/s |
| 140% | 0.1088 req/s | 1.4534 req/s |

The 80% point has stronger uncertainty evidence:

- mean TTFT reduction: 92.62%, cluster-bootstrap 95% CI [91.68%, 93.31%];
- p99 reduction across repeats: 95.70--95.83%;
- new-prefill reduction: 98.15%;
- goodput: 0.1727 -> 0.8307 req/s;
- absolute gain: 0.6580 req/s, 95% CI [0.5389, 0.7652];
- point multiplier: 4.81x, CI [2.85x, 12.61x].

Primary conclusion: **ContractKV converts prefix reuse into increasing absolute
SLO goodput as offered load rises, while native APC saturates near 0.1--0.17
compliant req/s.**

### Panel (b): tenant-density consolidation

Density-only rows, 100% authorized sharing:

| Tenants | Native APC goodput | ContractKV goodput |
|---:|---:|---:|
| 10 | 0.900 | 9.408 |
| 20 | 1.032 | 10.781 |
| 30 | 1.059 | 10.532 |
| 40 | 1.073 | 11.057 |
| 60 | 1.112 | 11.072 |
| 80 | 1.152 | 11.033 |

At a separate 40-tenant ON/OFF burst endpoint, raw -> ContractKV is:

- mean TTFT: 1364.5 -> 90.8 ms;
- SLO goodput: 1.064 -> 10.984 req/s;
- measured Jain fairness: 0.666 -> 1.000.

The density curve and burst endpoint must not be numerically mixed. The burst
fairness result is an observed association under the same trace, not a separate
fairness algorithm.

Primary conclusion: **with reusable templates resident, compliant throughput
stays near 11 req/s from 20 to 80 tenants instead of remaining near 1 req/s.**

### Panel (c): allocator-observed physical deduplication

At 80 tenants:

| Metric | Native APC | ContractKV | Change |
|---|---:|---:|---:|
| Peak used GPU KV blocks | 530 | 149 | -72% |
| Minimum free GPU KV blocks | 1856 | 2237 | +381 blocks |
| SLO goodput | 1.152 req/s | 11.033 req/s | +9.881 req/s |
| Dynamic-suffix reuse | 0 | 0 | no private suffix sharing |

Primary conclusion: **ContractKV removes duplicated physical stable-prefix
allocations, exposing real allocator headroom rather than merely reducing
token work.**

### Evidence sources

- `results/tsc_service/service_locality_aggregate_v0.csv`
- `results/tsc_service/service_locality_confidence_intervals_v0.csv`
- `results/tsc_service/multi_tenant_aggregate_v0.csv` (`kind=density` for the
  tenant curve)
- `docs/tsc_service_execution_closeout.md`
- `submission/claim_evidence_matrix.md`

### Claims to avoid

- Do not headline extreme ratios at 200--800% overload.
- Do not claim an infinite/unbounded capacity uplift.
- Do not infer GiB directly from new-prefill reduction.
- Do not imply that fairness improvement is a designed fairness mechanism.

---

## Fig. 6 - Operating Region and Frozen Benefit Gate

### Core question

**When does ContractKV help, and can it fail closed before spending verification
work in a locality regime with no expected return?**

### Recommended composition

Three panels:

- (a) authorized-sharing/locality knee;
- (b) working-set residency heatmap;
- (c) sealed held-out validation of the frozen net-benefit gate.

### Panel (a): measured sharing-ratio knee

| Authorized sharing | Mean TTFT reduction |
|---:|---:|
| 0% | 0.0% |
| 25% | 21.7% |
| 50% | 43.6% |
| 75% | 93.4% |
| 100% | 93.4% |

Primary conclusion: **the evaluated system has a sharp observed residency knee
between 50% and 75% sharing; this is a workload/cache-size operating point, not
a universal threshold.**

The zero-locality negative control remains important prose/appendix evidence:
ContractKV adds 1.6--8.7% mean-TTFT overhead when every stable prefix is unique.
It should not consume a main-panel slot once the frozen benefit gate exists.

### Panel (b): resident-prefix working set

Values are mean TTFT reduction:

| Active templates | Round-robin | Zipf |
|---:|---:|---:|
| 5 | 93.69% | 94.26% |
| 25 | 0.36% | 84.63% |
| 50 | 0.64% | 73.40% |

Primary conclusion: **ContractKV is governed by effective reuse distance, not
just nominal template count: skew preserves hot prefixes, while round-robin
thrashes once the working set exceeds cache capacity.**

### Panel (c): frozen net-benefit admission

The gate is frozen from the Qwen3-8B development grid: issue a certificate only
when both paths complete and expected future reuses are at least 10.

| Stable tokens | Future reuses | Tool slack | Frozen action | Reported held-out benefit |
|---:|---:|---:|---|---:|
| 1500 | 8 | 3500 ms | raw fallback | not claimed |
| 3000 | 12 | 500 ms | ContractKV | +7044.76 ms |
| 5000 | 10 | 1500 ms | ContractKV | +10842.68 ms |
| 3500 | 6 | 6000 ms | raw fallback | not claimed |

Results:

- 2/4 lanes accepted and 2/4 returned raw;
- both accepted lanes complete and pass quality sanity;
- 2/2 accepted lanes are observed net-positive;
- minimum accepted held-out benefit is 7044.76 ms;
- rejected lanes remain raw even if an offline diagnostic candidate happens to
  be positive.

Primary conclusion: **the gate is conservative and prospectively frozen: every
accepted sealed lane is actually profitable, while rejected lanes do not create
an unsafe post-hoc success claim.**

### Evidence sources

- `results/tsc_service/locality_residency_aggregate_v0.csv`
- `results/tsc_service/economics/heldout_gate_v1.csv`
- `results/tsc_service/economics/heldout_gate_v1_summary.json`
- `configs/tsc_net_benefit_gate_v1.json`
- `docs/pre_submission_experimental_closure_v1.md`

### Claims to avoid

- Do not call the gate a perfect learned predictor.
- Do not assign zero benefit to rejected lanes; write `raw fallback / not
  claimed` because the policy did not deploy the candidate.
- Do not say tool slack is universally available or free.
- Do not claim performance monotonicity outside the measured locality region.

---

## Cross-Figure Consistency Checklist

- **Figure numbering:** Fig. 1 is architecture; the five sections above are the
  manuscript's Fig. 2--Fig. 6 in order.
- **Model names:** use Qwen3-8B, Qwen3-14B (TP=2), Mistral-7B, and
  Llama-3.1-8B consistently.
- **Policy names:** D0 native APC, D1 frozen safe layout, D2 full ContractKV.
- **Latency:** mean, pooled p95, and pooled p99 must never be interchanged.
- **Goodput:** label absolute req/s; ratios are annotations, not the primary axis.
- **Quality:** distinguish official/frozen task metrics from marker sanity.
- **Safety:** `0/1,125 admitted compiled` is stronger and more accurate than
  claiming zero overall Llama variability.
- **Physical memory:** only Fig. 5(c)'s measured block counters support the 72%
  physical deduplication statement.
- **External systems:** matched-runtime deltas are causal; absolute cross-stack
  times are descriptive.
- **Evidence tier:** all performance panels are real serving. Deterministic
  325,000-transaction PSTP stress belongs in the safety table/text, not as a
  performance panel.

## Recommended One-Sentence Captions

- **Fig. 2:** ContractKV remains net-positive across four configurations while
  frozen qualification exposes model-specific safe reuse rather than forcing a
  universal layout.
- **Fig. 3:** On Llama, ContractKV offers the strongest measured
  performance--behavior trade-off; its residual tail is dominated by explicit
  L0 fallback, not admitted compiled requests.
- **Fig. 4:** Same-engine verification preserves the serving gain, and changing
  the certificate object from session to template reduces verification cost
  without changing the layout opportunity.
- **Fig. 5:** Certified reuse becomes absolute open-loop SLO goodput and 72%
  fewer allocator-observed used KV blocks at 80 tenants.
- **Fig. 6:** Locality and reuse distance define the operating region; a frozen
  benefit gate admits only sealed lanes with measured positive net return.
