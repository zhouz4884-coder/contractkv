# Phase 17R: Policy-Consistent Causality Closure

## Result

Phase 17R closes the promotion lineage with a versioned frozen policy manifest, same-run false-safe audit, Qwen3-8B source-level promotion loop, and mechanical incomplete taxonomy. The closeout is complete **with an explicit quiescence portability failure**, not with an unconditional deployment claim.

## A. Frozen Policy and Promotion Lineage

The [frozen manifest](../results/hard_systems/phase17r_frozen_policy_manifest_v0.json) binds the Qwen3-8B model config, tokenizer files, chat template, vLLM `0.10.2`, one-terminal-token protocol, calibration CSV hashes, fixed greedy decoding configuration, and policy hash `55e10dc4...df1ee4`.

Margins remain telemetry only. The frozen thresholds are intentionally non-decisional (`tau_raw=-1e9`, `tau_abs=-1e9`, `tau_drop=1e9`); exact answer path, strict unique top-1, and terminal consistency determine the intrinsic decision.

The [Qwen3-8B integrated result](../results/hard_systems/phase17r_qwen8b_integrated_v0.csv) passed 18/18 gates:

* 14 normal, conflict, shared-prefix, cancellation, missing-report, and disconnect cases carried consistent policy lineage through verifier, PSTP, and certificate.
* Four deliberate manifest mismatches (policy hash/threshold, model revision, terminal protocol, tokenizer hash) all ended `INCOMPLETE -> ABORTED`, with zero cache-entry delta and no certificate.
* Shared-prefix PASS/PASS performed one physical registration; PASS/FAIL isolated the failing transaction.

## B. Same-Run False-Safe Causality

The two previous held-out false-safe rows were audited with same-run raw free decode, three candidate free decodes, strict teacher forcing, and the same task-sanity evaluator. Both had matching candidate identity, runtime provenance, output token path, terminal token, and score:

| Case | Fresh raw/candidate score | Fresh drop | Old drop | Classification |
| --- | ---: | ---: | ---: | --- |
| LongBench/qasper/58 | 0.582677 / 0.582677 | 0.0 | 0.031358 | `STALE_OR_MISJOINED_QUALITY_LABEL` |
| LongBench/narrativeqa/165 | 0.285714 / 0.285714 | 0.0 | 0.050420 | `STALE_OR_MISJOINED_QUALITY_LABEL` |

The [token trace](../results/hard_systems/phase17r_false_safe_token_trace_v0.jsonl) retains all strict top-1 evidence. This is a data/provenance finding, not a reason to relax verifier gates.

All 34 historically unsafe labels were then re-scored: 29 remain unsafe, 3 are stale/nonreproducible, and 2 RepoBench candidates reached the frozen `max_tokens=96` limit and remain fail-closed. The [conditional refreshed summary](../results/hard_systems/phase17r_refreshed_unsafe_summary_v0.csv) has zero held-out unsafe certified after reclassifying only the three refreshed stale labels, but it is **not** a replacement for a full 734-row quality regeneration.

## C. Qwen3-8B Quiescence and Root Cause

The first 8B run exposed an implementation defect: `32` was applied per shadow request, allowing two requests to schedule `64` aggregate shadow tokens in one round. That is a code bug, not a model conclusion. The scheduler now enforces `CONTRACTKV_SHADOW_ROUND_TOKENS=32`; the corrected run records 1,207 shadow rounds with maximum aggregate and per-request shadow work both equal to 32.

The corrected fixed-parameter result is still above the frozen engineering budget:

| Condition | Foreground success | Verifier success | p95 TTFT | Penalty |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 60/60 | n/a | 1477.83 ms | 0.00 ms |
| Live verifier | 60/60 | 6/6 | 1497.35 ms | 19.51 ms |

There were zero mixed rounds and zero collisions. Consequently, the remaining failure is not token-cap leakage. It falsifies the *static cross-model wall-time portability* assumption: a 32-token budget and 10 ms target calibrated on Qwen3-4B cannot be deployed unchanged on Qwen3-8B. The data supports a future model/load-calibrated wall-time controller, but this phase does not tune one after observing the result.

## D. Incomplete Taxonomy

All 27 prior incomplete rows are classified in [phase17r_incomplete_taxonomy_v0.csv](../results/hard_systems/phase17r_incomplete_taxonomy_v0.csv), with no unknown category:

* `TARGET_TOKEN_ABSENT`: 25 rows, 23 safe and 2 unsafe, with 129,331 safe expected-prefix-gain unavailable because `top_logprobs=2` omitted the requested terminal/target token.
* `RAW_ATTESTATION_MISSING`: 2 safe rows.

This supports only the narrow claim that observed missing-evidence paths fail closed without cache mutation. It does not establish universal semantic-layout safety.

## Diagnosis

* **Code/protocol defects fixed:** duplicate EOS handling (Phase 17), aggregate rather than global shadow token accounting, and a zero-token cap accidentally applied to normal requests.
* **Data/provenance issue demonstrated:** three historical unsafe labels do not reproduce under the frozen current stack; two original false-safe claims were stale/misjoined.
* **Real systems boundary:** fixed token microchunk budgets do not guarantee fixed wall-time interference across model sizes.

The defensible next research direction is a model- and load-aware quiescence budget, while preserving the current immutable policy lineage and fail-closed transaction semantics.
