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
