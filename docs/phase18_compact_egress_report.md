# Phase 18: Source-Level Compact Egress Closeout

## Scope

Phase 18 C3/C4 moves ContractKV verification from a normal OpenAI completion
response to a source-level vLLM V1 control path. The implementation extends the
existing `EngineCoreRequest`, `EngineCoreOutput`, and `EngineCoreOutputs`
transport. It does not add a second ZMQ protocol or return prompt-logprob tensors
to the frontend.

The source branch is based on vLLM `v0.10.2` commit
`01efc7ef781391e744ed08c3292817a773d654e6`. The ContractKV patch commit is
`0a336eeb2a62198b8f6d27a079657df5e126a5c6` and is archived in
`patches/vllm-0.10.2-contractkv-compact-egress.patch`.

## Implementation

The dedicated `/v1/contractkv/verify` endpoint builds a native V1 request with
an optional verification spec. The scheduler consumes prompt-logprob tensors,
finalizes the fail-closed decision before request cleanup, and emits a compact
result through the existing EngineCore output transport. `AsyncLLM` partitions
compact outputs before the normal `OutputProcessor` and resolves a per-request
future. Normal chat and completion outputs retain the upstream path.

The implementation also supports the earlier quiescence mechanism in two modes:

- C3: polling through the per-round skipped-request queue;
- C4: event-driven parking outside the native waiting queue.

## Functional Gates

| Gate | Result |
| --- | --- |
| Normal API regression | 200/200 valid chat/completion requests succeeded |
| Compact smoke | PASS committed; FAIL, INCOMPLETE, and policy mismatch aborted |
| Sequential lifecycle | 100/100 succeeded |
| Concurrent lifecycle | 20/20 succeeded |
| Duplicate request ID | one accepted, one rejected; no future leak |
| Timeout/cancel/disconnect | all injected; pending futures remained zero |
| Shutdown during verify | client received HTTP 500; port and GPU state cleaned |
| Normal request after faults | HTTP 200 |

The smoke response was at most 432 bytes and contained no prompt-logprob field.
The measured full prompt-logprob HTTP response was 831,262 bytes. Mean compact
HTTP output was 387 bytes, a 2,147.96x reduction. With wire measurement enabled
only for the gate run, the largest serialized compact `EngineCoreOutput` was 231
bytes.

## C3/C4 Live Results

Each cell used Qwen3-8B, five fresh server processes, identical seeds, 100
foreground requests per condition per seed, and four verifier requests per seed.
Thus each cell contains 500 baseline foreground requests, 500 live foreground
requests, and 20 verifiers.

| Cell | Parking | Baseline p95 TTFT | Live p95 TTFT | Pooled delta | Mean per-seed delta | Median per-seed delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| C3 | polling | 8216.25 ms | 8211.45 ms | -4.80 ms | +12.81 ms | +13.17 ms |
| C4 | event-driven | 8205.38 ms | 8202.00 ms | -3.37 ms | -4.19 ms | -4.02 ms |

Both cells completed all foreground and verifier requests. Final router state was
zero pending futures, zero orphan outputs, and zero duplicate outputs.

The frozen statistical gates are deliberately separate:

| Gate | C3 | C4 |
| --- | --- | --- |
| Functional/lifecycle | PASS | PASS |
| Pooled systematic interference (<=10 ms) | PASS | PASS |
| Median paired-seed interference (<=10 ms) | FAIL | PASS |
| All-seed guard (<=10 ms) | FAIL | FAIL |

Accordingly, engineering closure passes, while per-seed tail determinism is not
established. See `docs/phase18_statistical_addendum.md` for the frozen wording.

The pooled result no longer shows the roughly +15 ms residual seen in the prior
full-egress C1/C2 screening. This supports compact egress as the mechanism that
removes systematic bulk-output interference. It does not establish an exact
15-to-negative millisecond causal effect because C1/C2 used a smaller earlier
workload. The 2,148x wire reduction is the direct causal evidence.

Parking does not have a stable latency effect. C4's mean and median paired deltas
are favorable, but the worst seed is +20.30 ms; C3 ranges from -34.10 to +58.39
ms. Parking remains a lifecycle-correctness mechanism, while per-seed tail jitter
under the 100-request stress burst remains a measurement concern.

## Root-Cause Classification

Three failures encountered during implementation were code or deployment defects,
not failures of the compact-egress idea:

1. `NaN` verifier telemetry was passed to strict JSON. It is now represented as
   `null` when unavailable.
2. Polling initially used `continue` without moving the denied shadow request,
   causing a scheduler busy loop. A later `break` attempt caused head-of-line
   blocking. Restoring the proven per-round skipped-request queue fixed both.
3. terminated API parents left orphan `VLLM::EngineCore` processes. The runner now
   identifies the actual GPU process and verifies an empty compute-process list
   before every fresh seed.

The remaining tail variability is not explained by these bugs. It is consistent
with queue and GPU scheduling noise under the deliberately saturated burst, and
should not be converted into a fixed wall-time LUT from this dataset.

## Decision

Compact egress is frozen as a valid ContractKV mechanism. The decision rule in
the Phase 18 plan only requires CUDA collision timing if the cleaned C3/C4 path
still has a systematic penalty near 10-15 ms. The pooled C3/C4 penalty is below
zero, so CUDA collision instrumentation is not required for this closeout. The
negative values are not claimed as acceleration.

The paper-safe claim is:

> A source-level vLLM V1 compact verification channel reduces verifier egress by
> more than three orders of magnitude and removes the earlier systematic p95
> foreground penalty in the pooled five-seed stress replay, while preserving
> normal API behavior and fail-closed transaction semantics.

It is not safe to claim that every seed improves or that parking itself is a
latency optimization.

## Code Used for Results

The following non-test files directly participated in producing this round:

- `patches/vllm-0.10.2-contractkv-compact-egress.patch`
- `scripts/install_vllm_v1_ephemeral_shadow_hook.py`
- `scripts/phase18_compact_egress_live.py`
- `scripts/phase18_compact_lifecycle_faults.py`
- `scripts/phase18_compact_quiescence_live.py`
- `scripts/run_phase18_compact_cells.sh`
- `scripts/phase18_summarize_compact_cells.py`
- `scripts/phase18_summarize_ablation.py`
- `scripts/phase17_live_common.py`
- `scripts/phase17_verifier_quiescence_live.py`
- `scripts/phase16e_live_transactional_slc.py`
- `scripts/contractkv_shadow_parking.py`
- `scripts/contractkv_quiescence.py`

## Evidence Files

- `results/hard_systems/phase18_c3_gate_summary_v1.json`
- `results/hard_systems/phase18_c3_c4_source_raw_v0.csv`
- `results/hard_systems/phase18_c3_c4_source_summary_v0.csv`
- `results/hard_systems/phase18_control_plane_ablation_summary_v0.csv`
- `results/hard_systems/phase18_c3_wire_summary_v0.json`
- `results/hard_systems/phase18_c3_lifecycle_faults_v0.json`
- `results/hard_systems/phase18_c3_shutdown_fault_v0.json`
- `results/hard_systems/phase18_source_branch_provenance_v0.json`
