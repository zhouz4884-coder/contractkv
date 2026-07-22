# Llama Quality Attribution and Tail Closure

This report closes the two residual questions in the five-repeat
Llama-3.1-8B comparison: the two observed material score differences and the
unchanged overall p95/p99 tail. It uses the existing 2,250 matched future
requests plus a 2,250-comparison cyclic raw-vs-raw control. No result is
removed from the observed distribution.

## 1. Repeated NarrativeQA Score Difference

Both observed drops map to `phase22r-narrativeqa-158`, turn 2, in repeats 1
and 4. In all five fresh processes:

- the frozen manifest requested L2;
- the L2 and L1 teacher-forced checks both returned `FAIL`;
- the controller issued no certificate;
- the served level was L0;
- `moved_stable_tokens` was zero.

The affected request therefore never consumed a ContractKV-compiled layout.
It is a fail-closed raw-order request.

The two output variants first diverge at Llama token position 26. The raw
variant has 35 output tokens and score 0.1667; the alternate variant has 39
tokens and score 0.1081. Repeats 1 and 4 pair the first variant in raw with
the second variant in the fallback cell. Repeat 5 produces the second variant
in both raw and fallback. A cyclic raw-vs-raw comparison also reproduces the
same 0.0586 score decrease between repeats 4 and 5.

| Quantity | Result |
|---|---:|
| Matched raw-vs-ContractKV comparisons | 2,250 |
| Observed material score decreases | 2 (0.089%) |
| Admitted-compiled material decreases | 0 (0.000%) |
| Cyclic raw-vs-raw material decreases | 1 (0.044%) |

The evidence supports runtime-control nondeterminism, not a layout-induced
regression. Cases B and C from the audit are inapplicable to this request:
there was no verifier `PASS`, no published layout, and no template certificate
covering the future request.

The historical Llama rows do not embed per-request generation, runtime, and
tokenizer hashes. The paired cells nevertheless use the same runner, model,
FP16 dtype, concurrency, max-token budget, prompt builder, and frozen protocol.
The missing row-level hashes remain a provenance limitation and are not
retroactively inferred.

## 2. Request-Level Tail Stratification

The pooled request distribution separates into three execution classes.

| Class | Requests | Mean TTFT | p95 | p99 | Delta vs paired raw | 1500-ms attainment |
|---|---:|---:|---:|---:|---:|---:|
| Admitted compiled | 1,125 (50%) | 263.29 ms | 699.50 ms | 898.96 ms | -68.30% | 100.0% |
| Manifest-direct L0 | 900 (40%) | 1261.76 ms | 1778.89 ms | 2311.01 ms | +0.33% | 71.1% |
| Runtime fallback | 225 (10%) | 865.68 ms | 1125.58 ms | 1129.17 ms | -15.20% | 100.0% |
| Overall mixture | 2,250 | 722.92 ms | 1716.74 ms | 2306.46 ms | -29.16% | 88.4% |

The certified half of the workload has substantially lower mean and tail
latency. The overall p95/p99 falls inside the deliberately retained L0 mass,
so the global tail is controlled by fail-closed coverage rather than the
compiled fast path. The runtime-fallback delta is descriptive only because
that class serves raw order and is not a ContractKV layout intervention.

## 3. Paper Claim

The defensible claim is:

> ContractKV observed two material paired score differences in 2,250 Llama
> requests, both on a fail-closed raw-order fallback and reproducible in the
> raw-only control. Among 1,125 admitted compiled requests, observed
> policy-attributable material regressions were zero. Certified requests
> reduced mean TTFT by 68.30% and achieved a 699.50-ms p95, while the overall
> tail remained dominated by deliberately unqualified L0 scopes.

This distinction preserves the observed 0.089% statistic while preventing a
runtime-control difference from being incorrectly attributed to ContractKV.

## Evidence

- `results/tsc_closure/llama_quality_root_cause_v1.json`
- `results/tsc_closure/llama_tail_stratification_v1.json`
- `results/tsc_closure/llama_tail_stratification_v1.csv`
- `results/tsc_closure/llama_sota_matrix_v1.json`
