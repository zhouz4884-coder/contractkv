# Llama-3.1-8B External Baseline Reproduction

## Frozen protocol

All complete cells use the same Llama-3.1-8B-Instruct weights, FP16, one RTX
3090, concurrency 2, 50 sealed sessions, 10 turns per session, 450 future
requests per repeat, 96 output tokens, and five fresh server processes. TTFT is
measured to the first streamed content token; task quality uses the frozen
RULER, LongBench, and RepoBench scorers.

## Real-runtime results

| Runtime / policy | Mean TTFT | p95 TTFT | 1500-ms goodput | New-prefill | Paired quality drop >0.03 |
|---|---:|---:|---:|---:|---:|
| vLLM APC, raw | 1020.44 ms | 1705.57 ms | 0.835 req/s | 2372.3 | reference |
| ContractKV | 722.92 ms | 1715.18 ms | 0.989 req/s | 1637.5 | 0.089% |
| Manual frozen oracle | 633.95 ms | 1710.56 ms | 1.056 req/s | 1434.7 | 1.733% |
| SGLang RadixAttention, raw | 911.45 ms | 1758.09 ms | 0.844 req/s | unavailable | reference |
| SGLang + frozen certified layout | 668.99 ms | 1764.49 ms | 0.999 req/s | unavailable | 0.089% |
| LMCache local CPU | 1078.92 ms | 1822.80 ms | 0.797 req/s | 2471.5 | reference |
| LMCache separator-only | 1011.88 ms | 1738.03 ms | 0.778 req/s | 2300.1 | reference |
| CacheBlend | 739.04 ms | 1002.20 ms | 1.028 req/s | 383.9 | 9.956% |

ContractKV reduces mean TTFT by 29.16% and raises SLO-goodput by 1.18x over
native vLLM APC. CacheBlend obtains a 26.96% mean-TTFT reduction over its
matched LMCache serialization, but 9.956% of paired requests lose more than
0.03 task score. ContractKV's corresponding rate is 0.089%. The frozen layout
also reduces mean TTFT by 26.60% on SGLang, showing that the compiler output is
portable; that row is an offline-layout diagnostic and is not described as an
online ContractKV deployment.

## CacheBlend compatibility closure

The supplied LMCache 0.3.9 path required three compatibility fixes before the
real algorithm could run on vLLM 0.10.2:

1. FlashInfer was pinned to 0.3.1, the API version named by LMCache's sparse
   backend. Older releases lack its shape validator and newer releases remove
   the block-sparse offset API.
2. JIT compilation was bound to an isolated CUDA 12.8 toolkit on the 8 TB disk;
   the host `/usr/local/cuda` points to CUDA 11.2.
3. LMCache's RoPE self-test hard-coded BF16 dummy tensors under an FP16 server.
   A reversible patch changes only those two validation tensors to FP16.

The final five runs contain 2500 connector events, 89.8% with positive hits,
82.94% mean hit fraction, zero engine-fatal events, and zero HTTP 500 responses.
Because layerwise mode disables incomplete-chunk storage, CacheBlend uses a
32-token chunk for the frozen 58--98-token segments; this avoids an otherwise
degenerate zero-hit configuration without changing request content.

## CacheSlide boundary

The supplied CacheSlide native path was executed after an exact Llama-3 RoPE
compatibility backport. It loaded the model, installed all 32 `hack_kv` layer
hooks, and exercised cached and uncached generation. It cannot enter the common
matrix: cache state is held in process-global `old_kvs` and
`cache_fuse_metadata`, which is not request-isolated at concurrency 2, and the
supplied Mistral-format entrypoint did not preserve Llama output equivalence.
The diagnostic cached path measured 228.12 ms versus 41.91 ms uncached and
failed output equivalence. No proxy number is substituted for the missing
common-protocol result.

## Evidence

- `results/tsc_closure/llama_sota_matrix_v1.json`
- `results/external_baseline/llama_lmcache_v1/runtime_accounting_v1.json`
- `results/external_baseline/artifact_audit/cacheblend_compatibility_v1.json`
- `results/external_baseline/artifact_audit/cacheslide_llama_smoke_v1.json`
