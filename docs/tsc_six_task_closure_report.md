# TSC Six-Task Experimental Closure

This report uses only fresh real-runtime measurements for performance claims. Deterministic protocol stress and external artifact failures are identified separately.

## 1. Llama-3.1-8B SOTA Direct Comparison

| Cell | Status | Repeats | Completion | Mean / p95 / p99 TTFT (ms) | SLO goodput | New-prefill | Score | Observed paired drop > 0.03 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| vLLM APC (raw order) | complete | 5 | 100.0% | 1020.44 / 1705.57 / 2292.98 | 0.835 | 2372.3 | 0.3538 | - |
| Manual stable-layout oracle (offline upper bound) | complete | 5 | 100.0% | 633.95 / 1710.56 / 2296.28 | 1.056 | 1434.7 | 0.3563 | 1.733% |
| ContractKV | complete | 5 | 100.0% | 722.92 / 1715.18 / 2304.68 | 0.989 | 1637.5 | 0.3537 | 0.089% |
| SGLang RadixAttention (raw order) | complete | 5 | 100.0% | 911.45 / 1758.09 / 2351.44 | 0.844 | unavailable | 0.3537 | - |
| SGLang RadixAttention + frozen certified layout | complete | 5 | 100.0% | 668.99 / 1764.49 / 2355.12 | 0.999 | unavailable | 0.3539 | 0.089% |
| LMCache local-CPU connector | complete | 5 | 100.0% | 1078.92 / 1822.80 / 2416.42 | 0.797 | 2471.5 | 0.3538 | - |
| LMCache matched separator baseline | complete | 5 | 100.0% | 1011.88 / 1738.03 / 2300.50 | 0.778 | 2300.1 | 0.3332 | - |
| LMCache CacheBlend (compatibility-shimmed lifecycle) | complete | 5 | 100.0% | 739.04 / 1002.20 / 1616.29 | 1.028 | 383.9 | 0.3398 | 9.956% |
| CacheSlide supplied artifact | external_artifact_blocked | - | - | - | - | - | - | - |

Matched-runtime deltas:

- ContractKV vs vLLM APC: 29.16% mean-TTFT reduction and 1.18x SLO-goodput.
- Frozen certified layout on SGLang vs raw RadixAttention: 26.60% mean-TTFT reduction; this is a portability diagnostic, not online ContractKV.
- CacheBlend vs its matched separator-only LMCache runtime: 26.96% mean-TTFT reduction.
- Descriptively, ContractKV is 2.18% faster in mean TTFT than CacheBlend while reducing paired >0.03 quality drops from 9.956% to 0.089%. The runtimes use their native prompt serialization, so matched-runtime deltas remain the causal comparisons.

Quality-attribution audit:

- The two observed ContractKV-vs-raw score drops (0.089% of paired requests) both occurred on the same fail-closed runtime-fallback request.
- Policy-attributable material regressions among admitted compiled requests: 0 (0.000%).
- A cyclic raw-vs-raw fresh-process control reproduced the same request-level change; its material-regression rate was 0.044%.
- The historical rows did not embed per-request generation/runtime hashes. The audit therefore uses execution-path evidence and reports this provenance limitation explicitly.

Request-level tail stratification:

| Request class | Share | Mean / p95 / p99 TTFT (ms) | Reduction vs paired raw | 1500-ms attainment |
|---|---:|---:|---:|---:|
| admitted_compiled | 50.0% | 263.29 / 699.50 / 898.96 | 68.30% | 100.0% |
| manifest_direct_l0 | 40.0% | 1261.76 / 1778.89 / 2311.01 | -0.33% | 71.1% |
| runtime_fallback | 10.0% | 865.68 / 1125.58 / 1129.17 | 15.20% | 100.0% |
| overall_mixture | 100.0% | 722.92 / 1716.74 / 2306.46 | 29.16% | 88.4% |

The admitted compiled half has a 699.50-ms p95 and 898.96-ms p99 with 100% 1500-ms attainment. The overall tail is controlled by deliberately retained L0 requests, not by certified compiled requests.

CacheSlide artifact status: `The supplied CacheSlide path executes, but its process-global old_kvs/cache_fuse_metadata state is not request-isolated for concurrency=2, and the supplied Mistral-format entrypoint does not preserve Llama-3.1 output equivalence. It is therefore excluded from the common 5x450-request service matrix rather than assigned a proxy number.`. The native KV-fusion path was executed after an exact Llama-3 RoPE compatibility backport, but it does not satisfy the frozen concurrency-2 common protocol; no proxy performance number is reported. Its diagnostic run loaded 32 hooked layers; cached TTFT was 228.1196117401123 ms and output-equivalence was `False`.

## 2. Same-Path D0/D1/D2

| Policy | Repeats | Completion | Mean TTFT (ms) | p99 TTFT (ms) | 500-ms E2E goodput | Drop |
|---|---:|---:|---:|---:|---:|---:|
| D0-native-apc | 5 | 100.00% | 2742.83 | 7531.79 | 0.066 | 0.00% |
| D1-frozen-safe | 5 | 100.00% | 194.95 | 935.86 | 1.472 | 0.00% |
| D2-template-contractkv | 5 | 100.00% | 194.72 | 935.86 | 1.428 | 0.00% |

D2 made 4.0 verifier endpoint calls per fresh process inside the serving engine, committed 4.0 templates, and had 0 registration failures. After charging registration wall time, D2 reduced mean TTFT by 92.90% and improved 500-ms SLO goodput by 21.49x over D0.

## 3. Frozen Net-Benefit Gate

The frozen held-out gate accepted 2/4 lanes. All accepted lanes were actually net-positive; the minimum observed benefit was 7044.76 ms.

## 4. Certificate Binding

All 15 signed-binding stress cases passed with 0 false admits and 0 false rejects. Unseen private suffixes remained admissible, while malicious metadata failed closed. Live D2 results additionally report zero scope-invalid admissions and zero certificate-binding failures.

## 5. PSTP State Machine

The formal PSTP stress covered 325,000 transactions, including a 32-client same-transaction contention run. Invariant failures were 0; aborted transactions with published blocks were 0. Live vLLM fault matrices remain separate evidence.

## 6. Five-Repeat Real-Task Open Loop

The matrix contains 3 policies x 5 fresh processes x 450 future requests. All closure gates pass: `{"all_completion_100pct": true, "d2_same_engine_verifier": true, "d2_zero_binding_failures": true, "d2_zero_quality_drop_gt_0_03": true, "d2_zero_scope_invalid": true}`. Registration and verifier wall time are charged to end-to-end goodput; quality uses the frozen RULER/LongBench/RepoBench scorers.

## Closure

Machine audit: `{"all_required_gates_pass": false, "claim_boundary": "A source-artifact blocker is not converted into a performance number or counted as a reproduced baseline.", "external_artifact_blockers": ["CacheSlide"], "schema_version": "contractkv.tsc-six-task-closure.v1", "tasks": [{"blocked_cell": "CacheSlide", "external_blocker": true, "name": "Llama SOTA direct comparison", "pass": false, "task": 1}, {"name": "same-serving-path D0/D1/D2", "pass": true, "task": 2}, {"name": "frozen net-benefit admission", "pass": true, "task": 3}, {"name": "certificate binding and lifecycle", "pass": true, "task": 4}, {"name": "PSTP state machine and concurrent faults", "pass": true, "task": 5}, {"name": "five-repeat real-task open-loop matrix", "pass": true, "task": 6}]}`
