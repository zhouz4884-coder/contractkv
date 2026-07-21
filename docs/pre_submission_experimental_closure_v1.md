# Pre-Submission Experimental Closure v1

## Scope and Claim Discipline

This closure packages the remaining serving-path, certificate-economics, and
external-runtime evidence before manuscript revision. All latency values below
come from real local serving runs unless explicitly labelled as a deterministic
state-machine test. Marker checks are not substituted for task scoring; the
task-bearing service-template audit is reported separately.

## 1. Corrected Source-Level PSTP Integration

The original Phase 17 harness was rerun after binding every runtime transaction
to an explicit `FrozenVerifierPolicy` and its `RuntimeIdentity`. The earlier
all-abort outcome was a harness/policy-binding mismatch, not an engine result.

- Integrated probe: 16/16 gate passes.
- Safe cases: 12 `PASS -> COMMITTED` transactions.
- Deliberate conflicts: 4 `FAIL -> ABORTED` transactions.
- A representative successful transaction committed 361 full stable-prefix
  blocks (5,776 tokens), reported 100% stable reuse on the later probe, and
  reported zero dynamic-suffix reuse.
- Concurrent/fault probe: 10/10 gate passes: cancellation, incomplete report,
  frontend disconnect, distinct-prefix isolation, and duplicate finalization
  all terminated in the expected state.

Evidence: `results/hard_systems/phase17_integrated_live_v0.csv`,
`results/hard_systems/phase17_concurrency_fault_v0.csv`, and
`results/hard_systems/phase17_integrated_events_v0.jsonl`.

Claim boundary: this is a live source-hook, compact-marker transactional probe
on Qwen3-4B, not a task-bearing quality benchmark.

## 2. Same-Queue Verifier Interference

The source-level compact verifier was issued through the live vLLM service path
alongside foreground requests. The earlier C3/C4 experiment contains 5 seeds,
500 foreground requests per condition, and 20 verifier requests.

- C3: pooled foreground p95 changed from 8,216.25 ms to 8,211.45 ms;
  the mean per-seed p95 penalty was 12.81 ms.
- C4: pooled foreground p95 changed from 8,205.38 ms to 8,202.00 ms;
  the mean per-seed p95 penalty was -4.19 ms.
- A lighter verifier-quiescence run measured 60 foreground requests per
  condition and 6 live verifier requests: p95 changed from 192.74 ms to
  199.60 ms (6.87 ms).

Evidence: `results/hard_systems/phase18_c3_c4_source_summary_v0.csv` and
`results/hard_systems/phase17_verifier_quiescence_summary_v0.csv`.

Claim boundary: these measurements establish real same-engine interference,
not a universal bound for every deployment workload.

## 3. Task-Bearing Service-Template Scope Audit

The service-template scope claim was checked with five real task families,
10 tenants per template, 10 turns per tenant, and three fresh-process pairs.

- 1,350 paired future outputs completed (100%).
- Raw and ContractKV mean task scores were both 0.356; paired difference was
  exactly 0.0 under the frozen metric.
- Zero paired quality violations beyond 0.03.
- Zero scope-invalid admissions, unauthorized reuse, and dynamic suffix reuse.
- Four qualified templates used shared certificates; unqualified Qasper was
  fail-closed to raw order.

Evidence: `results/tsc_service/service_template_quality_summary_v0.csv` and
`results/tsc_service/service_template_quality_gate_v0.json`.

## 4. Controlled Certificate-Granularity Ablation

The D2 session/template comparison fixes the same 25-tenant trace and safe
layout, separating verification-object economics from prefix locality.

| Policy | Verifier calls | Mean new-prefill tokens | Mean TTFT | p99 TTFT |
| --- | ---: | ---: | ---: | ---: |
| D2-session | 125 | 50.17 | 64.02 ms | 89.51 ms |
| D2-template | 5 | 41.67 | 62.91 ms | 88.02 ms |

Both D2 variants completed all requests with marker sanity, no unauthorized
cross-domain reused hashes, and zero dynamic-suffix reuse. The template
certificate therefore changes verification economics (25x fewer calls) rather
than creating a hidden prefix-locality advantage.

Evidence: `results/tsc_service/certificate_granularity_ablation_v0.csv` and
`results/tsc_service/certificate_granularity_ablation_gate_v0.json`.

## 5. Frozen Net-Benefit Admission Gate

The gate was selected only from the existing Qwen3-8B development grid:
admit only when a certificate is issued, both paths complete, and
`future_reuses >= 10`. Its 28 accepted development lanes all had positive
observed net benefit; the smallest was 918.16 ms.

Four new sealed operating points were then executed on Qwen3-8B:

| Stable tokens | Future reuses | Slack | Frozen action | Observed net benefit |
| ---: | ---: | ---: | --- | ---: |
| 1,500 | 8 | 3,500 ms | raw fallback | not claimed |
| 3,000 | 12 | 500 ms | ContractKV | 7,044.76 ms |
| 5,000 | 10 | 1,500 ms | ContractKV | 10,842.68 ms |
| 3,500 | 6 | 6,000 ms | raw fallback | not claimed |

All accepted held-out lanes completed and passed marker sanity; both measured
net benefits were positive. The two rejected lanes are intentionally reported
as raw fallback even though their diagnostic candidate runs happened to be
positive. This is a conservative operating-region gate, not a learned online
benefit predictor.

Evidence: `configs/tsc_net_benefit_gate_v1.json`,
`results/tsc_service/economics/heldout_gate_v1_raw.csv`,
`results/tsc_service/economics/heldout_gate_v1.csv`, and
`results/tsc_service/economics/heldout_gate_v1_summary.json`.

## 6. External Runtime and SOTA Compatibility

On the sealed Llama-3.1-8B trace, SGLang 0.4.9.post6 with RadixAttention
consumed layouts selected by vLLM-issued session certificates. Across three
fresh raw/certified pairs (450 future requests per repeat):

- raw mean TTFT: 916.69 ms;
- certified-layout mean TTFT: 668.54 ms (27.07% lower);
- both completed all requests;
- certificate-qualified future fraction: 50%; other futures used raw fallback;
- paired task-score shift: +0.000283; 1/1,350 paired outputs dropped by more
  than 0.03.

This establishes layout portability to an external RadixAttention runtime. It
does not claim that online verification or PSTP was transplanted into SGLang.

CacheSlide, CacheBlend, PromptCache, and LMCache were source-audited. Their
checked source trees respectively pin vLLM 0.8.5, Torch 2.2.1, Torch 2.3.0 with
Transformers 4.34, and a current LMCache development build whose runtime
requirements include Transformers >=5.4. An isolated LMCache preflight was
performed against the CUDA-12.8 base stack: the command-line shell imported,
but the full server failed before launch because its unstaged runtime
dependencies (including `sortedcontainers` and the compiled `lmcache.c_ops`)
were absent; `pip check` also reported the incompatible Transformers
requirement. Completing that installation would replace the vLLM 0.10.2
environment's Transformers 4.55.2 with a version outside its tested range.
These systems therefore require isolated, version-matched reproductions; no
cross-stack number is reported as a same-stack direct comparison.

Evidence: `results/external_baseline/llama_radix_certified/summary_v1.csv`,
`results/external_baseline/llama_radix_certified/summary_v1.json`, and
`third_party/external_baselines/` on the experiment server.

## 7. Deterministic PSTP State-Machine Stress

An independent in-memory state-machine stress test executed 100,000
transactions at each of 1, 8, and 32 simulated clients. Each configuration
committed 59,933 transactions and aborted 40,067 injected-fault transactions;
all invariant checks passed. The stress test verifies state-machine transitions
and publication invariants, while the source-hook probes above establish the
real-vLLM path.

Evidence: `results/tsc_closure/pstp_state_machine_stress_v1.csv` and
`results/tsc_closure/pstp_state_machine_stress_v1.json`.
