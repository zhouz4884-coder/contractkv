# ContractKV Submission Hardening Closeout

## Decision

The research phase is frozen. Submission hardening is complete: certificate
scope is explicit in code and documentation, Qwen and Mistral core cells have
three fresh-process repetitions, the external prefix-cache baseline status is
recorded, and a minimal hash-audited artifact plus paper package is generated.

## Main repeated result

| Model | Net mean TTFT reduction (bootstrap 95% CI) | p95 TTFT reduction | New-prefill reduction | SLO-goodput gain | Scope-invalid admitted |
|---|---:|---:|---:|---:|---:|
| Qwen | 37.81% [36.95%, 38.33%] | 33.03% | 59.13% | 183.24% | 0 |
| Mistral | 31.72% [31.36%, 32.21%] | -0.20% | 39.46% | 26.08% | 0 |

## External baseline

The B1-B4 matrix uses identical model-specific traces, concurrency, output limits, dtype, and three fresh processes. On SGLang, the offline frozen safe layout reduces mean TTFT versus raw RadixAttention by 54.93% for Qwen and 35.53% for Mistral; p95 changes are 34.66% and 0.07%, respectively. B4 demonstrates compiler-layout portability only: it has no online PSTP or certificate issuance. SGLang prefix-token counters come directly from server logs and include Turn 0; vLLM counters cover future requests only. SGLang physical block IDs remain unavailable rather than inferred from timing.

| Model | Cell | Runtime | Mean TTFT ms | p95 TTFT ms | Input tokens | Prefix-hit tokens | Observed new-prefill total | SLO req/s | Task score | Peak KV |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen | B1 | vLLM-0.10.2-APC | 1396.42 | 2774.37 | 3530.12 | 83.20 | 4653342.00 | 0.41 | 0.39 | 522 blocks |
| Qwen | B3 | vLLM-0.10.2-APC | 633.74 | 1857.91 | 3530.12 | 2121.35 | 1901838.00 | 1.16 | 0.39 | 737 blocks |
| Mistral | B1 | vLLM-0.10.2-APC | 1102.49 | 2200.52 | 2704.52 | 101.12 | 3514590.00 | 0.64 | 0.33 | 397 blocks |
| Mistral | B3 | vLLM-0.10.2-APC | 698.37 | 2204.79 | 2704.52 | 1128.50 | 2127630.00 | 0.81 | 0.33 | 571 blocks |
| Qwen | B2 | SGLang-0.4.9-RadixAttention | 1417.37 | 2921.15 | 3530.12 | 87.26 | 1721438.00 | 0.40 | 0.33 | 12765 token slots |
| Qwen | B4 | SGLang-0.4.9-RadixAttention | 638.80 | 1908.62 | 3530.12 | 1919.55 | 805292.00 | 1.14 | 0.33 | 12765 token slots |
| Mistral | B2 | SGLang-0.4.9-RadixAttention | 1026.23 | 2347.26 | 2704.52 | 118.37 | 1301572.00 | 0.65 | 0.30 | 10229 token slots |
| Mistral | B4 | SGLang-0.4.9-RadixAttention | 661.56 | 2345.64 | 2704.52 | 1042.46 | 839529.00 | 0.87 | 0.31 | 10229 token slots |

## Qualified Llama replay

A development-only all-session gate prospectively qualifies `RULER:niah_single_1` and rejects every other Llama task family to raw order. Across 3 fresh-process held-out repeats, the qualified path reduces net mean TTFT by 86.63%, p95 TTFT by 84.51%, and new-prefill work by 95.45%. Fresh paired task scoring covers 270 future outputs with 0 quality violations and 0 scope-invalid admissions. This is empirical cross-model success inside a frozen task-family scope, not universal Llama support.

## Physical deduplication

| Agents | Same-snapshot dedup blocks | Dedup KV GiB | Initial alloc raw/Contract | Peak used raw/Contract | Peak-used KV GiB saved | TTFT reduction | Refcount match | OOM-free lower bound |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 2309.00 | 5.07 | 259.00/3.00 | 1284.00/288.00 | 2.19 | 96.48% | 100.00% | >=20 |
| 20 | 4878.00 | 10.72 | 259.00/3.00 | 1386.00/318.00 | 2.35 | 96.95% | 100.00% | >=20 |

The primary dedup value is measured in one scheduler snapshot as logical shared references minus unique physical block IDs, net of the raw-order cell. Block-pool high-water supplies an independent peak check. Qwen's actual GQA geometry and float16 block size convert blocks to bytes. Cross-lifecycle block-ID reuse is diagnostic only, and new-prefill reduction is never used as a memory proxy.

## Claim discipline

The paper claims real vLLM prefix-work, TTFT, and SLO behavior only in the
measured qualified scopes. It does not claim universal certificates, real KV
offload or quantization, production-cluster throughput, or full benchmark
leaderboard accuracy.

## Actual result-producing code in this hardening round

- `scripts/contractkv_certificate_scope.py`
- `scripts/contractkv_transaction.py`
- `scripts/phase17_live_common.py`
- `scripts/install_vllm_v1_phase17_hook.py`
- `scripts/phase19b_end_to_end_live.py`
- `scripts/run_submission_repeats.sh`
- `scripts/summarize_submission_repeats.py`
- `scripts/install_sglang_external_baseline.sh`
- `scripts/run_external_sglang_raw_replay.py`
- `scripts/run_external_sglang_baseline.sh`
- `scripts/summarize_external_system_matrix.py`
- `scripts/run_remaining_submission_experiments.sh`
- `scripts/freeze_llama_task_qualification.py`
- `scripts/run_llama_qualified_replay.sh`
- `scripts/score_llama_qualified_replay.py`
- `scripts/phase14m_physical_dedup.py`
- `scripts/run_physical_dedup_submission.sh`
- `scripts/summarize_physical_dedup_memory.py`
- `scripts/repair_submission_scope_telemetry.py`
- `scripts/generate_submission_package.py`
- `scripts/build_paper_artifact.py`

Historical modules imported by the final request path are enumerated in the
artifact manifest. Test files are intentionally not listed here.
