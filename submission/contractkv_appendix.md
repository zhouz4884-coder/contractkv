# ContractKV Submission Appendix

## A. Frozen fresh-process protocol

- Back end: vLLM 0.10.2, prefix caching enabled.
- Hardware: two RTX 3090 GPUs; each paired policy cell occupies one GPU.
- Load: concurrency 2, max model length 8,192, max sequences 2.
- Repetition: three fresh server processes per model-policy cell.
- Counterbalancing: GPU assignment alternates; repeat 2 reverses launch order.
- Workload: same sealed model-specific trace, ten turns, turn 0 unmeasured.
- Accounting: net TTFT adds verification time not hidden by 2,000 ms slack.
- SLO: 1,500 ms TTFT.

## B. Per-repeat paired data

| Model | Repeat | Raw mean TTFT | Contract net mean TTFT | Net reduction | p95 reduction | New-prefill reduction | SLO-goodput gain |
|---|---:|---:|---:|---:|---:|---:|---:|
| mistral | 1 | 1098.30 | 753.92 | 31.36% | -0.77% | 39.46% | 21.24% |
| mistral | 2 | 1110.70 | 753.00 | 32.21% | 0.90% | 39.46% | 35.65% |
| mistral | 3 | 1098.47 | 751.48 | 31.59% | -0.73% | 39.46% | 21.35% |
| qwen | 1 | 1389.11 | 875.85 | 36.95% | 33.05% | 59.13% | 181.58% |
| qwen | 2 | 1406.18 | 869.68 | 38.15% | 33.57% | 59.13% | 184.98% |
| qwen | 3 | 1393.97 | 859.65 | 38.33% | 32.48% | 59.13% | 183.17% |


## C. Certificate invalidation matrix

| Change | Observation scope | Qualified-session scope |
|---|---|---|
| Model identity | invalidate | invalidate |
| Task family | invalidate | invalidate |
| Dependency-valid layout | invalidate | invalidate |
| Stable-prefix content | invalidate | invalidate |
| Policy hash | invalidate | invalidate |
| Observation identity/epoch | invalidate | permitted only under frozen qualification |
| Qualification hash | not used | invalidate |

## D. External baseline boundary

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

External status: `complete`. Official SGLang interfaces used by the
reproduction script are the OpenAI-compatible serving endpoint, streaming
latency path, metrics option, and `--disable-radix-cache` ablation. ContractKV
is not reimplemented inside SGLang.

## E. Reproduction entry points

```bash
bash scripts/run_submission_repeats.sh
bash scripts/install_sglang_external_baseline.sh
bash scripts/run_external_sglang_baseline.sh
bash scripts/run_llama_qualified_replay.sh
bash scripts/run_physical_dedup_submission.sh
python scripts/generate_submission_package.py
python scripts/build_paper_artifact.py
```

All models, Hugging Face caches, conda packages, logs, and raw request results
remain on the 8 TB data volume. Git tracks source, summarized evidence, and
hash manifests only.

## F. Current-runtime relevance: vLLM 0.25.1

An appendix-only audit replays five RULER and five LongBench HotpotQA cases on
an unmodified official vLLM 0.25.1 wheel, with native APC and three fresh server
processes. The frozen compiled layout reduces mean TTFT by 79.84% on RULER and
96.77% on HotpotQA, and reduces observed new-prefill work by 94.20% and 99.53%.
All 60 requests complete; every paired raw/compiled output is identical and
the task-score delta is zero.

The source audit finds the V1 admission, lookup, allocation, and block
registration objects, and the audited files match the installed wheel
manifest. Native vLLM still exposes a longest prefix chain rather than
arbitrary non-contiguous segment reuse. The audit therefore establishes
current-version structural relevance, while changed cache-publication
interfaces require a version-specific PSTP adaptation. It is not presented as
a full ContractKV port to vLLM 0.25.1.
