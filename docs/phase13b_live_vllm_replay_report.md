# Phase 13B Live vLLM Replay Report

## Scope

Phase 13B completed the live endpoint replay for the four policies:

```text
vLLM raw-order
ContractKV-CAPOSC
ContractKV-CAPOSC + SSPP
ContractKV-CAPOSC + SSPP + RAR
```

B-1 used concurrency 1/2/4 with SLO buckets 300/500/700 ms. B-2 used concurrency 6/8/10. The endpoint was Qwen3-8B on vLLM 0.10.2 at `localhost:8001`, with prefix caching enabled and `max_num_seqs=2`.

## Live results

The machine-readable sources are:

```text
results/end_to_end/phase13b_live_b1_raw_v0.csv
results/end_to_end/phase13b_live_b1_summary_v0.csv
results/end_to_end/phase13b_live_b2_standard_raw_v0.csv
results/end_to_end/phase13b_live_b2_standard_summary_v0.csv
results/end_to_end/phase13b_live_b2_rar_raw_v0.csv
results/end_to_end/phase13b_live_b2_rar_summary_v0.csv
```

In B-1, all policies completed all 10 requests at each tested concurrency. The observed mean TTFT at concurrency 1 was 108.51 ms for raw-order, 94.72 ms for CAPOSC, 98.23 ms for CAPOSC+SSPP, and 97.96 ms for CAPOSC+SSPP+RAR. At concurrency 4, the corresponding means were 450.35, 451.70, 416.13, and 407.63 ms. This is a live serving observation, not a modeled ledger result.

In B-2, the endpoint completed the recorded workload for the standard and RAR cells without HTTP capacity failures. Mean TTFT remained pressure-dominated, reaching roughly 1.1--1.3 s in the recorded RAR cells. The RAR summary reports seven RAR records per concurrency cell, 137 freed blocks per cell, and 445 recompute tokens saved per cell; the companion JSONL contains real vLLM anchor-actuator events with positive free-GPU-block deltas, retained prefix blocks, freed suffix blocks, and completed requests.

## Real task quality scoring

The quality supplement is written to:

```text
results/end_to_end/phase13b_real_task_quality_raw_v0.jsonl
results/end_to_end/phase13b_real_task_quality_summary_v0.csv
```

It reuses real Qwen3-8B outputs from the existing RULER `niah_single_1`, LongBench `hotpotqa`/`qasper`/`narrativeqa`, and RepoBench Python-completion sanity subset. The scoring uses answer containment/token-F1 as a task sanity score; it is not an official LongBench or RepoBench submission.

`vllm-raw-order` and `contractkv-caposc` are directly scored from real model outputs. `contractkv-caposc-sspp` and `contractkv-caposc-sspp-rar` are explicitly marked `projected_from_real_caposc_output`: these execution layers do not change prompt text or answer semantics, so their quality is inherited from the real CAPOSC output. They are not falsely presented as independent generations.

The superseded Phase 12C projection showed a 0.333333 RepoBench drop for unrestricted canonical-slot. That value must not be attributed to CAPOSC. The direct provenance is now corrected to `reused_phase12c_real_qwen3_8b_output`, and the fresh policy-aligned replay below is the Phase 13B quality result.

## Phase 13B-Q fresh policy-aligned replay

The fresh replay uses the same 15 real task samples and regenerates four layouts against Qwen3-8B:

```text
raw-order
canonical-all (unsafe analysis baseline)
static-posc
contractkv-caposc (actual cache-aware compiler output)
```

Artifacts:

```text
results/end_to_end/phase13bq_fresh_quality_raw_v1.jsonl
results/end_to_end/phase13bq_fresh_quality_summary_v1.csv
scripts/phase13b_fresh_policy_quality_replay.py
```

The replay uses a 2600-word context-safe subset so LongBench failures are not confused with the vLLM 8K capacity boundary. RepoBench repository context is modeled as an ordered supernode: the tool observation may move only as a whole around the code component, while code-internal order is preserved.

Fresh results show that raw-order, static-POSC, and CAPOSC choose the same RepoBench layout and have identical mean score (`0.074074` on this three-sample sanity subset). Their quality drop versus raw is `0.000000`. `canonical-all` produces dependency violations on all three RepoBench samples, but this small subset does not show a score drop; therefore the result is a semantic-safety warning, not evidence of quality collapse. The earlier `0.333333` number remains a valid Phase 12C unrestricted-canonical observation, but is not a Phase 13B CAPOSC result.

For LongBench hotpotqa, CAPOSC preserves raw-order score (`0.083333`) while canonical-all reaches `0.333333` on this subset. This reinforces that canonical-all and CAPOSC are different policies; CAPOSC is not allowed to claim canonical-all's quality or speed behavior.

## Interpretation and boundaries

The live endpoint evidence supports:

1. CAPOSC, SSPP preparation, and RAR fields can traverse the live request path.
2. B-1 records real TTFT/TPOT/latency and complete requests at concurrency 1/2/4.
3. B-2 records pressure behavior and companion RAR actuator events with positive free-block deltas.
4. The real task supplement preserves an explicit quality boundary instead of treating marker sanity as benchmark quality.

SSPP `real_lightweight` measures actual Python-side preparation and slack coverage. It does not subtract preparation time from measured vLLM TTFT and does not by itself prove asynchronous overlap. RAR claims use the companion actuator log; planned CSV fields alone are not sufficient. The quality subset is a task sanity evaluation, not an official benchmark score.

## Artifacts

```text
scripts/phase13b_live_replay.py
scripts/phase13b_real_task_quality_eval.py
tests/test_phase13b_live_replay.py
tests/test_phase13b_real_task_quality_eval.py
```
