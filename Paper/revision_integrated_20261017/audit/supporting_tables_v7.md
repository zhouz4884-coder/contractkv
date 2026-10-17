# Supporting tables: keep operating protocols separate

Generated from the same source manifest as the figures. No new GPU measurements were run.

## A. Additional Qwen six-source validation (separate source set)

These six sources differ from the six-source three-model main validation. The cost variant was rejected as the default.

| Policy | Full wall / raw | Compiled future pairs | Coverage |
| --- | --- | --- | --- |
| Strict raw-witness, original cost gate | 1.803x | 774 / 1,620 | 47.78% |
| Cost-adapted candidate (not selected) | 1.070x | 258 / 1,620 | 15.93% |

## B. Original deployment latency with tool-slack accounting

Net mean TTFT charges verification exposure beyond the frozen tool-slack window. These rows retain the original input and deployment protocols.

| Model/configuration | Tool slack | Net mean TTFT reduction | Fresh-process pairs |
| --- | --- | --- | --- |
| Mistral-7B | 2,000 ms | 31.72% | 3 |
| Qwen3-8B | 2,000 ms | 37.81% | 3 |
| Qwen3-14B TP=2 | 2,000 ms | 44.69% | 3 |
| Llama-3.1-8B | 6,000 ms | 29.41% | 3 |

## C. Matched-native quality distributions (no cross-stack speed ranking)

| Method | Own matched baseline | Pairs | Baseline mean | Method mean | Score up >0.03 | Score down >0.03 | No material change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CacheBlend (adapted LMCache path) | LMCache separator-matched raw | 2250 | 0.333210 | 0.339817 | 331 | 224 | 1695 |
| ContractKV (vLLM) | vLLM APC raw | 2250 | 0.353780 | 0.353744 | 0 | 2 | 2248 |
| Manual layout oracle (offline) | vLLM APC raw | 2250 | 0.353780 | 0.356323 | 60 | 39 | 2151 |
| SGLang frozen certified layout | SGLang raw RadixAttention | 2250 | 0.353739 | 0.353874 | 2 | 2 | 2246 |

## D. Frozen prospective gate (moved from Fig. 6)

| Stable tokens | Reuse count | Tool slack (ms) | Gate accepted | Actual route | Observed net benefit (ms) |
| --- | --- | --- | --- | --- | --- |
| 1500 | 8 | 3500 | False | raw-fallback | 0.00 |
| 3000 | 12 | 500 | True | ContractKV | 7044.76 |
| 5000 | 10 | 1500 | True | ContractKV | 10842.68 |
| 3500 | 6 | 6000 | False | raw-fallback | 0.00 |

Rejected lanes report the actual raw-fallback route. The two accepted lanes are not evidence that every workload is profitable.

## E. Density goodput retained from the original Fig. 5

The density study uses class-specific TTFT thresholds (750/1,500/3,000 ms). Its ALL goodput is a separate metric from the 500-ms curve in Fig. 5(a).

| Registered identities | Policy | Class-specific SLO goodput (req/s) | Peak used blocks | Minimum free blocks |
| --- | --- | --- | --- | --- |
| 10 | D0-native-apc | 0.900 | 525.7 | 1860.3 |
| 10 | D2-full-contractkv | 9.408 | 146.0 | 2240.0 |
| 20 | D0-native-apc | 1.032 | 530.0 | 1856.0 |
| 20 | D2-full-contractkv | 10.781 | 149.0 | 2237.0 |
| 30 | D0-native-apc | 1.059 | 530.0 | 1856.0 |
| 30 | D2-full-contractkv | 10.532 | 149.0 | 2237.0 |
| 40 | D0-native-apc | 1.073 | 530.0 | 1856.0 |
| 40 | D2-full-contractkv | 11.057 | 149.0 | 2237.0 |
| 60 | D0-native-apc | 1.112 | 530.0 | 1856.0 |
| 60 | D2-full-contractkv | 11.072 | 149.0 | 2237.0 |
| 80 | D0-native-apc | 1.152 | 530.0 | 1856.0 |
| 80 | D2-full-contractkv | 11.033 | 149.0 | 2237.0 |

## F. Primary strict-validation tail and full-route results

| Model | Raw readiness p99 (ms) | CKV readiness p99 (ms) | p99 reduction 95% source/repeat CI (%) | Future material drops (all routes) |
| --- | --- | --- | --- | --- |
| Qwen3-8B | 8561.8 | 9146.6 | [-56.247, 26.802] | 0 |
| Mistral-7B | 9418.2 | 9511.3 | [-60.576, -0.137] | 0 |
| Llama-3.1-8B | 7851.3 | 7905.7 | [-16.784, 0.151] | 3 |

Full wall throughput gains coexist with these tail costs. The future-only table excludes the additional Mistral initial-business material drop recorded in the full experimental report.

| Audit | Audited / compiled sources | Compiled future pairs | Compiled output-ID differences | Raw-positive compiled pairs | All-route future material drops |
| --- | --- | --- | --- | --- | --- |
| Earlier bounded-input audit | 50 / 12 | 2442 | 0 | 2442 | 33 |
| Faithful held-out validation | 6 / 4 | 1296 | 0 | 1032 | 3 |

## G. Primary new-prefill accounting (counts per process)

| Model | Raw business | CKV business | Certification incl. witness | CKV total | Count reduction |
| --- | --- | --- | --- | --- | --- |
| Qwen3-8B | 6,008,336 | 3,204,304 | 73,580 | 3,277,884 | 45.44% |
| Mistral-7B | 7,074,492 | 5,986,864 | 51,760 | 6,038,624 | 14.64% |
| Llama-3.1-8B | 5,822,228 | 5,149,118 | 38,807 | 5,187,925 | 10.89% |

Counts are initial scheduler observations, rather than an integral of GPU kernels or a VRAM estimate.


## H. Task-family coverage (faithful primary validation)

| Model | Family | Compiled future pairs | Coverage | Inherited family L0 |
| --- | --- | --- | --- | --- |
| Qwen3-8B | HotpotQA | 516 / 810 | 63.70% | False |
| Qwen3-8B | RepoBench | 168 / 810 | 20.74% | False |
| Mistral-7B | HotpotQA | 342 / 810 | 42.22% | False |
| Mistral-7B | RepoBench | 0 / 810 | 0.00% | True |
| Llama-3.1-8B | HotpotQA | 270 / 810 | 33.33% | False |
| Llama-3.1-8B | RepoBench | 0 / 810 | 0.00% | True |

## I. Mean readiness timing (same primary validation)

| Model | Raw mean (ms) | CKV mean (ms) | Mean reduction | Source/repeat 95% interval for reduction (%) |
| --- | --- | --- | --- | --- |
| Qwen3-8B | 4443.34 | 2494.18 | 43.87% | [5.640, 79.479] |
| Mistral-7B | 5158.25 | 4534.70 | 12.09% | [-0.350, 34.781] |
| Llama-3.1-8B | 4194.66 | 4027.27 | 3.99% | [1.550, 5.724] |

## J. Earlier-audit raw-positive count recheck by metric family

The 2,442/2,442 positive-score count is reproduced from every compiled pair. It combines distinct scorer-credit definitions and is not a unified correctness or accuracy claim.

| Task family | Study | Scorer-credit group | Compiled future pairs | Raw score >0 | Raw score =0 |
| --- | --- | --- | --- | --- | --- |
| NarrativeQA | template-fanout | QA F1 credit | 174 | 174 | 0 |
| RULER | single-session | string-match credit | 630 | 630 | 0 |
| RULER | template-fanout | string-match credit | 1548 | 1548 | 0 |
| RepoBench | template-fanout | code similarity credit | 90 | 90 | 0 |

## K. Logged sequence included in Fig. 3(c)

The case selector takes the first issued certificate in file order and its first matching witness/future; equality and publication checks then validate that fixed selection.

| Field | Observed value |
| --- | --- |
| source_group | LongBench:hotpotqa:hotpotqa:doc:69 |
| query_scope | b93a2dbf1318b4625a593f5f2db91d73ce1198dc2242dac079f49fc4d4bca332 |
| raw_request_id | chatcmpl-template-fanout_qwen_risk-tail_r1-r4f-heldout-8306ed450c777c06-tenant00-t0 |
| verification_request_id | template-fanout_qwen_risk-tail_r1-single-r4f-heldout-8306ed450c777c06-b93a2dbf1318b4625a593f5f2db91d73ce1198dc2242dac079f49fc4d4bca332 |
| future_request_id | chatcmpl-template-fanout_qwen_risk-tail_r1-r4f-heldout-8306ed450c777c06-tenant00-t3 |
| raw_turn | 0 |
| future_turn | 3 |
| output_ID_count | 7 |
| output_token_ids | [151667, 271, 151668, 271, 9454, 13, 151645] |
| output_ID_SHA256 | 10ad9b016a93e4776d7623eaf3e78fa349d120f27dc0e1264d00997334ce75e9 |
| verification_decision | PASS |
| txn_state | COMMITTED |
| committed_full_blocks | 888 |
| committed_tokens | 14208 |
| later_native_hit_tokens | 14240 |
| certificate_hash | 5dcea1c8af53649db18bdd4bcba26846e0776609430ceea608ea28d7ee2bddc9 |

Exact selected records, per-line hashes, upstream full-file SHA256 and line indices are in `trace_log_excerpt_v7.json`. The compact source bundle carries the selected records; full primary archives support independent re-extraction.

## L. Density block/goodput values come from the same cells

| Policy | Cell | Repeat | SLO goodput | Peak used blocks | Minimum free blocks |
| --- | --- | --- | --- | --- | --- |
| D0-native-apc | tsc-tenant-density_r1_D0-native-apc_n80_s1p0 | 1 | 1.1645371366913513 | 530 | 1856 |
| D0-native-apc | tsc-tenant-density_r2_D0-native-apc_n80_s1p0 | 2 | 1.148800059677507 | 530 | 1856 |
| D0-native-apc | tsc-tenant-density_r3_D0-native-apc_n80_s1p0 | 3 | 1.1425668431028895 | 530 | 1856 |
| D2-full-contractkv | tsc-tenant-density_r1_D2-full-contractkv_n80_s1p0 | 1 | 11.074508875029247 | 149 | 2237 |
| D2-full-contractkv | tsc-tenant-density_r2_D2-full-contractkv_n80_s1p0 | 2 | 10.965259674475828 | 149 | 2237 |
| D2-full-contractkv | tsc-tenant-density_r3_D2-full-contractkv_n80_s1p0 | 3 | 11.058439437418333 | 149 | 2237 |

This density experiment is a bounded-concurrency wave replay with tiered SLOs. It is distinct from the fixed open-arrival 500-ms curve.

## M. Access-pattern prefix-hit statistics

| Templates | Access pattern | Net mean TTFT reduction | CKV prefix-hit ratio |
| --- | --- | --- | --- |
| 5 | round_robin | 93.686% | 98.188% |
| 5 | zipf | 94.258% | 98.296% |
| 25 | round_robin | 0.363% | 0.000% |
| 25 | zipf | 84.629% | 83.435% |
| 50 | round_robin | 0.645% | 0.000% |
| 50 | zipf | 73.397% | 69.570% |

## N. Process-repeat statistics (markers omitted from Fig. 2)

| Model | Aggregate throughput / Raw | Repeat 1 | Repeat 2 | Repeat 3 | Min-max |
| --- | --- | --- | --- | --- | --- |
| Qwen3-8B | 1.619040 | 1.614757 | 1.622596 | 1.619755 | [1.614757, 1.622596] |
| Mistral-7B | 1.109072 | 1.109678 | 1.110186 | 1.107357 | [1.107357, 1.110186] |
| Llama-3.1-8B | 1.070281 | 1.068091 | 1.071230 | 1.071521 | [1.068091, 1.071521] |

| Model | Policy | Repeat 1 mean readiness (ms) | Repeat 2 (ms) | Repeat 3 (ms) |
| --- | --- | --- | --- | --- |
| Qwen3-8B | raw-order | 4428.82 | 4471.52 | 4429.66 |
| Qwen3-8B | risk-tail | 2491.06 | 2506.26 | 2485.21 |
| Mistral-7B | raw-order | 5167.38 | 5142.33 | 5165.02 |
| Mistral-7B | risk-tail | 4545.76 | 4514.06 | 4544.28 |
| Llama-3.1-8B | raw-order | 4186.66 | 4217.87 | 4179.45 |
| Llama-3.1-8B | risk-tail | 4021.62 | 4052.53 | 4007.65 |
