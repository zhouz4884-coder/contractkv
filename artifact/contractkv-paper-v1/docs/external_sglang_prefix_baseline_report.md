# External SGLang Prefix-Cache Baseline

## Purpose

This A-tier baseline asks whether a production RadixAttention substrate alone
recovers reuse from the unchanged raw-order agent trace. It does not port
ContractKV to SGLang.

## Frozen setup

- Same Qwen3-8B and Mistral-7B checkpoints and model-specific sealed traces as the main repeat.
- Concurrency 2, ten turns, turn 0 warm-up, 8,192-token context.
- B1: vLLM APC with raw order (reused from the main repeat).
- B2: SGLang RadixAttention with raw order.
- B3: vLLM APC with online verified compiled order (reused from the main repeat).
- B4: SGLang RadixAttention with offline frozen safe compiled order.
- Isolated conda-first environment and caches on the 8 TB data volume.
- SGLang uses its Triton attention backend and PyTorch sampler because the host CUDA 11.2 toolkit cannot JIT the cu12 FlashInfer wheel; RadixAttention remains enabled in every SGLang cell.

## Result

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

## Evidence boundary

The runner reports streaming TTFT, TPOT, completion, prompt tokens, and SLO
goodput. Cached/new-prefill counts are read from SGLang's real server log and
their all-request scope (including Turn 0) is explicit; no cache hit is
reconstructed from timing. Physical block IDs remain unavailable. The launch and ablation interfaces
follow the official SGLang serving and observability documentation:

- https://docs.sglang.ai/developer_guide/bench_serving
- https://docs.sglang.ai/advanced_features/observability.html
