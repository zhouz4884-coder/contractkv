# Phase 19B: Task-Bearing End-to-End Live Replay

## Scope

Phase 19B connects the frozen Qwen3-8B certificates from Phase 19A to physical
future-turn prefix reuse on a fresh vLLM 0.10.2 endpoint. The replay uses 50
untouched sessions: ten each from RULER, LongBench HotpotQA, NarrativeQA,
Qasper, and RepoBench. None overlaps the Phase 19A quality pool.

Each session has ten turns. Four policies and three load tiers produce 6,000
auditable rows: 600 unmeasured turn-0 initialization/canary rows and 5,400
measured future requests. Every policy/load cell measures the same 450
session-turn keys (turns 1--9).

## Fair Replay Protocol

Each policy/load cell starts a fresh vLLM process with an empty automatic
prefix cache. Qwen3-8B runs at 8K context, `max_num_seqs=2`, greedy decoding,
`max_tokens=96`, and prefix caching enabled. Load tiers use concurrency 1, 2,
and 4. Independent cells run in pairs on the two RTX 3090 GPUs and do not share
ports, prefix state, metrics files, or server processes.

The final protocol fixes four implementation/measurement defects found during
the audit: all policies now treat turn 0 as unmeasured initialization; the
replay and frozen decode contract both use 96 output tokens; new-prefill work
is total prompt tokens minus physical prefix-hit tokens rather than the first
chunk scheduled by chunked prefill; and dynamic-suffix reuse is computed above
the exact prompt-token longest common prefix. The final dynamic-suffix metric
is zero in every ContractKV cell.

`contractkv-full` runs a raw-layout canary, same-backend teacher-forced strict
top-1 verification, transactional commit or fail-closed fallback, and then
physical-cache-aware future turns only for certified sessions. Net TTFT adds
verifier latency left after a 2,000 ms tool-slack window.

## Main Results

| Load | Concurrency | Raw mean TTFT | ContractKV observed TTFT | Unhidden verifier / future | ContractKV net TTFT | Net reduction | Raw / ContractKV new-prefill | Raw / ContractKV SLO req/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Low | 1 | 875.07 ms | 398.49 ms | 161.67 ms | 560.16 ms | 35.99% | 3446.92 / 1408.77 | 0.503 / 0.879 |
| Transition | 2 | 1387.04 ms | 650.54 ms | 158.66 ms | 809.20 ms | 41.66% | 3446.92 / 1408.77 | 0.212 / 1.046 |
| Saturation | 4 | 2403.33 ms | 1285.61 ms | 167.06 ms | 1452.66 ms | 39.56% | 3446.92 / 1408.77 | 0.115 / 0.736 |

At a 1,000 ms TTFT SLO, ContractKV improves compliant request rate by 74.86%,
393.04%, and 539.34% over raw order. Total new-prefill work falls by 59.13%
at every tier, and the verified policy retains 59.79% of the prefix-work gain
available to the unsafe physical-cache-aware upper bound. Completion is 100%.

Certificates are issued for 34 of 50 sessions (68%). No unsafe session is
certified. Certified stable-prefix physical reuse is 99.98%, while measured
dynamic-suffix reuse is zero. ContractKV has zero task-quality violations at
the frozen `quality_drop > 0.03` threshold and mean quality drop 0.00008064.
The 2.0--2.22% strict output-contract mismatch is token/format telemetry and is
not the task-quality gate.

## Interpretation

The fair replay supports a causal Qwen3-8B system claim: certified layout
changes real vLLM prefix work, reduces total new prefill, and improves net warm
TTFT and SLO-compliant request rate after charging unhidden verification cost.
Unverified layouts are faster but have a 2% quality-violation rate, showing why
transactional verification is part of the system rather than bookkeeping.

This is repository task-sanity scoring, not official full-dataset leaderboard
scoring. The server has a 1,300-row unified pool and 761 live-serving candidates;
the balanced 50-session split is a controlled systems experiment, not a claim
that every benchmark example has been run.

## Audit Gates

All strong gates pass: aligned future counts and turns, complete unmeasured
turn 0, zero unsafe certification, safe coverage at least 50%, zero quality
violations, certificate coverage at least 50%, certified stable-prefix reuse
at least 95%, zero dynamic-suffix reuse, net TTFT reduction at least 30%, and
new-prefill reduction at least 40%.

## Actual Code Used

- `scripts/phase19b_build_task_sessions.py`
- `scripts/phase19b_end_to_end_live.py`
- `scripts/phase19b_summarize_net_benefit.py`
- `scripts/run_phase19b.sh`
- `scripts/install_vllm_v1_prefix_metrics_probe.py`
- `scripts/run_vllm_server.sh`
- `scripts/stop_vllm_server.sh`
- `scripts/contractkv_pstp.py`
- `scripts/contractkv_frozen_policy.py`
- `scripts/contractkv_verifier.py`
- `scripts/phase12e_cache_aware_posc.py`
- `scripts/phase12f_real_vllm_caposc_replay.py`
- `scripts/phase12_task_quality_sanity.py`
- `scripts/phase13b_fresh_policy_quality_replay.py`
- `scripts/phase14c_run_full_pool_quality_jobs.py`
- `scripts/phase15d_task_bearing_certified_replay.py`
- `scripts/phase17_live_common.py`

## Evidence

- `results/end_to_end/phase19b_untouched_sessions_v0.jsonl`
- `results/end_to_end/phase19b_task_replay_raw_v0.jsonl`
- `results/end_to_end/phase19b_task_replay_summary_v0.csv`
- `results/end_to_end/phase19b_task_replay_gate_v0.json`

Raw per-cell scheduler events and server logs remain on the 8 TB server volume.
