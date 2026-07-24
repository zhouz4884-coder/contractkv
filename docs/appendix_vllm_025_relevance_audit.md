# Appendix Audit: ContractKV Relevance on vLLM 0.25.1

## Purpose and claim boundary

This appendix audit asks whether the structural premise and required hook
objects behind ContractKV remain relevant in vLLM 0.25.1. It is deliberately
not a claim that the frozen vLLM 0.10.2 ContractKV source patch can be applied
unchanged. The experiment uses a frozen, previously qualified compiled layout
on native vLLM automatic prefix caching (APC); it does not run online
qualification, certificate issuance, or PSTP inside vLLM 0.25.1.

## Frozen protocol

- Runtime: official installed `vllm==0.25.1+cu129`; audited source files match
  the wheel `RECORD`.
- Model: Qwen3-8B, `float16`, one RTX 3090, native prefix caching enabled.
- Workload: five RULER `niah_single_1` cases and five LongBench HotpotQA cases.
- Cells: native raw order versus the same frozen compiled order.
- Repetition: three fresh vLLM server processes; 60 measured requests total.
- Serving limits: `max_model_len=20000`, `max_num_seqs=1`,
  `max_tokens=64`.
- Metrics: OpenAI streaming TTFT/TPOT and native `/metrics` counters for local
  cache-hit and local-compute prompt tokens.
- Quality: paired raw/compiled task scores and exact output equality.

The server host exposes CUDA 11.2 as `/usr/local/cuda`, whereas the vLLM wheel
uses CUDA 12.9. FlashInfer sampler JIT therefore cannot compile against the
system toolkit. The audit disables only the optional FlashInfer sampler through
`VLLM_USE_FLASHINFER_SAMPLER=0`; both layouts use the same setting, and no vLLM
source file is modified. All caches, logs, and results are routed to the 8 TB
data volume.

## Real serving results

| Workload | Layout | Completion | Quality pass | Mean TTFT | p95 TTFT | Prefix-hit tokens | New-prefill tokens |
|---|---|---:|---:|---:|---:|---:|---:|
| RULER | raw | 100% | 100% | 295.66 ms | 302.48 ms | 32 | 1,172 |
| RULER | compiled | 100% | 100% | 59.59 ms | 66.56 ms | 1,136 | 68 |
| HotpotQA | raw | 100% | 60% | 4,754.28 ms | 5,402.30 ms | 32 | 15,658.2 |
| HotpotQA | compiled | 100% | 60% | 153.60 ms | 174.79 ms | 15,616 | 74.2 |

The compiled layout reduces RULER mean TTFT by **79.84%** and observed
new-prefill work by **94.20%**. On the longer HotpotQA prompts, it reduces mean
TTFT by **96.77%** and new-prefill work by **99.53%**. Repeat-level mean TTFT is
stable: RULER compiled is 58.92--60.14 ms versus 293.64--298.06 ms raw;
HotpotQA compiled is 150.79--158.11 ms versus 4,732.55--4,769.58 ms raw.

Raw and compiled outputs are exactly equal for every paired request
(`paired_output_equal_rate=1.0`), with mean and minimum task-score deltas of
zero. RULER exact retrieval passes all cases. HotpotQA's absolute 60% pass rate
is identical across both layouts; this five-case adapted audit is not presented
as an official LongBench score. Its role is to show that the measured serving
gain is not caused by a policy-attributable behavior change.

## Source-level portability audit

| Requirement | vLLM 0.25.1 status | Evidence |
|---|---|---|
| Request-time layout admission | open | `Scheduler.add_request` is present |
| Native prefix observation | open | `KVCacheManager.get_computed_blocks` is present |
| Allocation control point | open | `KVCacheManager.allocate_slots` is present |
| Cache publication point | present, adaptation required | `KVCacheManager.cache_blocks` and `BlockPool.cache_full_blocks` are present |
| Partial-block registration | present but not non-contiguous reuse | `cache_partial_block` remains prefix-chain metadata |
| Frozen source patch drop-in | blocked | signatures and publication internals changed |

All six audited objects are available and all audited source files match the
installed wheel manifest. Native vLLM still finds the longest prefix-chain hit;
it does not discover arbitrary non-contiguous stable segments. This is exactly
the structural blind spot addressed by ContractKV's certified layout compiler.
The admission, lookup, allocation, and publication objects remain available,
but PSTP must be adapted to the new publication interfaces before claiming a
full current-version implementation.

## Result classification

**This is a good result.** It provides strong appendix evidence that (1) the
structural opportunity persists on vLLM 0.25.1, (2) the frozen compiled layout
produces large real reductions in prefix work and TTFT without changing paired
outputs, and (3) the required V1 object classes still exist. It does not prove
that online verification or transactional publication has already been ported;
therefore it strengthens current-version relevance without changing the main
paper's implementation boundary.

## Artifacts

- `results/appendix/vllm_025/vllm_025_structural_audit_raw.jsonl`
- `results/appendix/vllm_025/vllm_025_structural_audit_summary.csv`
- `results/appendix/vllm_025/vllm_025_hook_portability_audit.json`
- `results/manifests/vllm_025_relevance_audit.yaml`
- `submission/appendix_vllm_025_relevance.tex`
