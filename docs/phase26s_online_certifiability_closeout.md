# Phase 26S: Online Certifiability and Economic Closure

## Objective

Phase 26S tests the deployable statement left open by Phase 26R: a strict
observation-scoped verifier must be both quality-safe under independent TP=2
decode and economically positive after charging any work not hidden by tool
slack.

## Frozen Protocol

- Model: DeepSeek-Coder-V2-Lite-Instruct, bfloat16, TP=2 on two RTX 3090 GPUs.
- Workload: 50 fresh sessions, five families, ten turns per session.
- Policies: vLLM raw, Exact-only mechanism diagnostic, and ContractKV with a
  verification-before-admission gate.
- Repeats: three fresh processes per policy, with rotated policy order.
- Concurrency: two; prefix caching enabled.
- Candidate-margin q05 threshold: 1.25, frozen from the maximum v5 false-safe
  boundary plus a 0.15 numerical reserve.
- Declared tool slack: 7000 ms.
- Economic rule: one observation is charged one reuse; verification is admitted
  only when its frozen family p95 preparation fits slack and Wilson-LCB
  expected saved prefill time remains positive.
- Typed Tier-B is disabled because no deterministic typed family has the
  preregistered 125 safe admissions. Open-QA lexical F1 remains diagnostic.

The frozen policy is
`results/cross_model/deepseek_phase26r_scope_closure/frozen_observation_policy_v2.json`.
The formal split commitment is
`results/cross_model/deepseek_phase26r_scope_closure/sealed/split_commitment_v6.json`.

## Results

<!-- PHASE26S_RESULTS_BEGIN -->
All nine cells completed (`1500` live requests per policy). Aggregate results:

| Policy | Certificate coverage | New-prefill reduction | Mean TTFT | P95 TTFT | Net mean TTFT reduction | Net P95 reduction | Quality violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vLLM raw | 0.00% | 0.00% | 357.95 ms | 806.98 ms | 0.00% | 0.00% | 0 |
| Exact-only diagnostic | 9.93% | 8.29% | 333.92 ms | 750.06 ms | -890.42% | -1806.59% | 0 |
| ContractKV economic gate | 7.73% | 4.13% | 344.32 ms | 804.82 ms | **3.73%** | **0.27%** | 0 |

Exact-only confirms that the strengthened numerical gate removed the v5
false-safe on `1500` observations. It is nevertheless economically invalid:
mean unhidden verifier cost was 3211.33 ms and p95 was 14791.26 ms. ContractKV
admitted verification for all 300 RULER observations and rejected all 1200
LongBench/RepoBench observations before paying raw-attestation or compact
verification cost. It issued 116 Exact certificates. Mean unhidden cost fell
to 0.29 ms and p95 to 0 ms.

The net mean reduction was stable in sign across fresh processes; tail latency
remained near noise level and changed sign in repeat 2:

| Repeat | Coverage | New-prefill reduction | Net mean TTFT reduction | Net P95 reduction |
| --- | ---: | ---: | ---: | ---: |
| 1 | 6.80% | 3.63% | 2.19% | 0.28% |
| 2 | 8.20% | 4.39% | 2.34% | -0.93% |
| 3 | 8.20% | 4.38% | 6.63% | 1.65% |

Within the prospectively admitted RULER scope, certificate coverage was
38.67%, new-prefill fell 35.82%, and net mean TTFT fell 22.58%, with zero
quality violations. The other four families used raw fallback and are included
in the global row. Completion was 100%; scope-invalid rows, quality violations,
and certified dynamic-suffix reuse were all zero.

The safety and bounded-deployment gates pass. The preregistered broad gate
(`>=50%` coverage, `>=30%` new-prefill reduction, and `>=25%` net mean TTFT
reduction) does not pass.
<!-- PHASE26S_RESULTS_END -->

## Interpretation Boundary

Exact-only is a mechanism diagnostic, not a deployable policy, because it pays
verification for all families. ContractKV is the online policy: it may choose
raw fallback for most observations, and that conservative coverage is part of
the global result. The offline task-safe recoverability upper bound remains an
oracle analysis and is not reported as online coverage.

DeepSeek-V2-Lite is a 2.4B-active MoE with MLA. Consequently, avoided prefill
tokens have less wall-clock value than on a dense 14B model, and MLA changes KV
geometry. Phase 26S reports real vLLM token/block telemetry and does not infer
GQA-equivalent GiB savings.

## Root Cause: Code, Design, or Model

All three matter, but at different layers:

1. **Code/protocol robustness:** v5's candidate-margin threshold `1.0` allowed
   two independent TP=2 decodes to diverge after a teacher-forced PASS. A
   frozen `1.25` threshold removed this observed false-safe in all 1500 v6
   Exact observations. Earlier cache-salt and suffix-accounting fixes were also
   required for valid physical attribution.
2. **Control-plane design:** observation-scoped safety means verifier cost
   cannot be amortized over future turns. Exact-only's catastrophic net result
   is therefore structural, not an accounting bug. The pre-verification
   economic gate is the necessary systems mechanism.
3. **Model/runtime boundary:** DeepSeek-V2-Lite activates about 2.4B MoE
   parameters per token and uses MLA. Its raw prefill is cheaper and KV geometry
   is smaller than a dense 14B GQA model, so each avoided token has less
   wall-clock and memory value. ContractKV still produces a real positive
   result where the reusable prefix is large, but broad five-family gains do
   not follow from the model's 16B total parameter count.

The result is therefore not "ContractKV does not generalize." It is a bounded
generalization result: physical reuse, safety, and positive net benefit survive
on MLA+MoE, while the online-certifiable profitable region is narrower than on
Qwen/Mistral. Offline task-safe divergence cannot be substituted for that
online region.

## Executed Production Code

The exact non-test file inventory is frozen in
`results/cross_model/deepseek_phase26r_scope_closure/phase26s_result_manifest_v6.json`.
The primary executed entry points were `run_phase26r_observation_scoped.sh`,
`phase26r_observation_live.py`, `phase26r_policy.py`,
`phase26r_typed_contracts.py`, `contractkv_verifier.py`, the three vLLM source
hook installers, and `phase26r_analysis.py`. Split preparation, pilot
calibration/diagnosis, and closeout were generated by the corresponding
`phase26r_prepare_fresh_heldout.py` and `phase26s_*.py` scripts.
