# ContractKV Submission Supplementary Experiments

## Decision

The supplementary experiment batch is complete. It strengthens the paper along
three independent evidence axes: global safe serving gains, high gains inside a
prospectively qualified scope, and deterministic token/block-work mechanisms.
All headline serving cells use real vLLM endpoints. Offline re-thresholding and
bootstrap analyses reuse frozen request-level live logs and do not replace live
measurements.

## Frozen protocol

- Qwen3-8B and Mistral-7B use 50 held-out sessions, 10 turns, concurrency 2,
  and three fresh server processes per cell.
- The layout decomposition compares native vLLM APC raw order (D0), an offline
  frozen-safe compiled layout with raw fallback and no online verification (D1),
  and full online ContractKV (D2). D1 and D2 optimize exactly the same frozen
  session scopes: 68% for Qwen and 50% for Mistral.
- The extended Llama replay uses 30 new source-group-disjoint RULER sessions,
  10 turns, three fresh raw/ContractKV process pairs, and the prospectively
  frozen L3 policy. The selected split has zero source-group and sample overlap
  with prior development and held-out splits.
- Session-cluster bootstrap resamples fresh-process repeats and paired sessions,
  rather than treating requests from one session as independent.

## Main global result

| Model and scope | Net mean TTFT reduction (session-cluster 95% CI) | Net TTFT speedup | New-prefill reduction | Prefill-work speedup | 1500 ms SLO goodput multiplier |
|---|---:|---:|---:|---:|---:|
| Qwen3-8B, all held-out workflows | 37.81% [29.84%, 45.51%] | 1.61x | 59.13% | 2.45x | 2.64x |
| Mistral-7B, all held-out workflows | 31.72% [23.73%, 39.74%] | 1.46x | 39.46% | 1.65x | 1.24x |
| Llama-3.1-8B, new qualified RULER replication | 85.97% [85.64%, 86.29%] | 7.13x | 95.45% | 21.96x | 4.22x |

The Llama row is deliberately qualified-scope evidence and is not a global
Llama claim. Qwen and Mistral are the all-workflow global rows.

## Same-runtime layout decomposition

| Model | Cell | Mean TTFT | p95 TTFT | New-prefill tokens/request | SLO req/s | Task score | Optimized coverage |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen | D0 raw APC | 1396.42 ms | 2774.37 ms | 3446.92 | 0.411 | 0.388962 | 0% |
| Qwen | D1 frozen-safe layout | 623.01 ms | 1851.59 ms | 1407.56 | 1.176 | 0.388881 | 68% |
| Qwen | D2 online ContractKV | 633.74 ms serving / 868.39 ms net | 1857.91 ms | 1408.77 | 1.163 serving | 0.388881 | 68% |
| Mistral | D0 raw APC | 1102.49 ms | 2200.52 ms | 2603.40 | 0.645 | 0.328636 | 0% |
| Mistral | D1 frozen-safe layout | 695.83 ms | 2195.02 ms | 1574.60 | 0.821 | 0.328787 | 50% |
| Mistral | D2 online ContractKV | 698.37 ms serving / 752.80 ms net | 2204.79 ms | 1576.02 | 0.811 serving | 0.328784 | 50% |

D1 isolates the benefit of consuming the frozen safe layout on the same vLLM
runtime. It reduces mean TTFT by 55.39% (2.24x) for Qwen and 36.89% (1.58x)
for Mistral, while task-score deltas versus raw are -0.000081 and +0.000151.
Full online verification adds a conservatively amortized 245.38 ms/request for
Qwen and 56.98 ms/request for Mistral. This decomposition makes both the layout
benefit and the remaining control-plane optimization opportunity explicit.

## Deterministic token-work evidence

| Model and scope | Repeats | New-prefill reduction | Work speedup | Observed tokens saved across repeats | Repeat range |
|---|---:|---:|---:|---:|---:|
| Qwen3-8B, all workflows | 3 | 59.13% | 2.45x | 2,751,504 | 0 |
| Mistral-7B, all workflows | 3 | 39.46% | 1.65x | 1,386,960 | 0 |
| Llama-3.1-8B, prior qualified RULER set | 3 | 97.06% | 33.99x | 336,480 | 0 |
| Qwen3-14B TP=2, limited scale-up | 3 | 60.57% | 2.54x | 1,393,680 | 0 |

Exact repeat invariance means determinism under the frozen prompts, manifests,
and server configuration. It is not a claim of hardware-independent latency.
The 30-session Llama extension independently reports 95.45% reduction; the
difference from the prior 10-session row reflects the broader source-disjoint
sample set, not nondeterminism within either frozen set.

## SLO sensitivity

The table uses the conservative net-amortized verifier accounting. It reports a
curve rather than choosing one favorable threshold after seeing the result.

| Model | SLO | Raw req/s | ContractKV req/s | Multiplier |
|---|---:|---:|---:|---:|
| Qwen3-8B | 500 ms | 0.081 | 0.624 | 7.71x |
| Qwen3-8B | 750 ms | 0.162 | 0.658 | 4.07x |
| Qwen3-8B | 1000 ms | 0.209 | 0.738 | 3.52x |
| Qwen3-8B | 1500 ms | 0.411 | 1.085 | 2.64x |
| Qwen3-8B | 3000 ms | 0.788 | 1.300 | 1.65x |
| Mistral-7B | 500 ms | 0.082 | 0.394 | 4.80x |
| Mistral-7B | 750 ms | 0.161 | 0.533 | 3.31x |
| Mistral-7B | 1000 ms | 0.414 | 0.533 | 1.29x |
| Mistral-7B | 1500 ms | 0.645 | 0.800 | 1.24x |
| Mistral-7B | 3000 ms | 0.774 | 0.942 | 1.22x |

## Physical deduplication closure

The 20-agent Qwen experiment separates same-snapshot sharing from lifecycle
peak occupancy:

- 5,140 logical shared references map to 257 unique physical blocks, a 20.0x
  same-snapshot deduplication factor.
- Net of the raw cell, 4,878 duplicate physical allocations are avoided. Qwen's
  measured GQA KV geometry converts this logical duplicate capacity to 10.72
  GiB. This is not presented as lifecycle peak memory saving.
- The independent block-pool high-water measurement falls from 1,386 to 318
  used blocks: 1,068 blocks or 77.06%, equal to 2.35 GiB of peak KV occupancy.
- Minimum free blocks rise from 1,000 to 2,068 (2.07x headroom), refcount matching
  is 100%, and the observed OOM-free concurrency lower bound is at least 20.

No memory claim is inferred from new-prefill tokens. The memory rows come from
physical block IDs, reference counts, and block-pool counters.

## Extended Llama qualified replay

Across 30 new source-disjoint sessions and three fresh process pairs, all 1,800
requests complete. ContractKV issues 30/30 session certificates in every repeat.
The 810 paired future outputs have raw score 1.0, ContractKV score 1.0, zero
quality violations, and zero scope-invalid admissions. Mean TTFT falls from
approximately 450 ms to 63 ms; p95 falls by 84.13%; and 1500 ms SLO goodput
rises from 3.42 to 14.42 req/s. This supports strong cross-model behavior in a
prospectively qualified scope while preserving the global Llama boundary.

## Problems found and resolved

1. The first D1 attempt applied the compiled layout to every session. Its roughly
   94% TTFT reduction was an oracle-like canonicalize-all upper bound, not a
   frozen-safe decomposition. It was excluded and rerun with exactly the D2
   qualified session set plus raw fallback. This was an experimental-semantics
   implementation error, not evidence against the ContractKV mechanism.
2. Cold model reads occasionally exceeded the fixed startup polling window by a
   few seconds. Startup polling is now configurable; the default behavior is
   unchanged, and supplement runners use a wider fresh-load window.
3. Resume logic previously accepted any nonempty output. It now requires the
   exact expected request count, preventing partial cells from being skipped.
4. Standalone summary scripts now add the repository root to `sys.path`, making
   remote invocation independent of the caller's working-directory import state.

After these corrections, every final live cell has its exact expected row count,
100% completion, and no residual vLLM process or installed probe hook.

## Claim boundary

The defensible paper claim is that ContractKV reduces real prefix work and real
vLLM TTFT while preserving task behavior in measured, prospectively qualified
scopes, and that this translates into SLO and physical block-pool benefits. The
results do not establish universal model/task qualification, hardware-independent
latency, real KV offload or quantization, or production-cluster throughput.

## Actual result-producing code in this batch

- `scripts/phase19b_end_to_end_live.py`
- `scripts/run_vllm_server.sh`
- `scripts/stop_vllm_server.sh`
- `scripts/run_layout_only_decomposition.sh`
- `scripts/summarize_layout_only_decomposition.py`
- `scripts/summarize_submission_supplement.py`
- `scripts/prepare_extended_ruler_sessions.py`
- `scripts/run_extended_ruler_replay.sh`
- `scripts/summarize_extended_ruler.py`
- `scripts/summarize_submission_repeats.py`
- `scripts/score_llama_qualified_replay.py`
- `scripts/install_vllm_v1_ephemeral_shadow_hook.py`
- `scripts/install_vllm_v1_prefix_metrics_probe.py`

Test files are intentionally excluded from this list.

## Common-scope cross-model addendum

The final sample-symmetry experiment replays Qwen, Mistral, and Llama on the
same frozen 30 RULER sessions. The model-stratified macro result is 86.67% net
mean TTFT reduction, 96.01% new-prefill reduction, and 3.31x SLO-goodput, with
2,430 paired future outputs and zero quality violations. Full protocol and
claim boundaries are in `docs/common_ruler_cross_model_report.md`.
