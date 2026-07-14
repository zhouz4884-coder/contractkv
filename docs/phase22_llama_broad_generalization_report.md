# Phase 22: Llama Broad-Scope Generalization

## Result

ContractKV passes the preregistered paper-level generalization gate on
Llama-3.1-8B-Instruct. The final sealed experiment covers all five task
families, includes raw-order fallback in every global metric, and uses three
fresh raw/ContractKV server pairs.

| Global metric | Raw | ContractKV | Delta |
| --- | ---: | ---: | ---: |
| Mean TTFT | 1021.95 ms | 721.37 ms | -29.41% |
| P95 TTFT | 1708.91 ms | 1713.71 ms | +0.28% |
| Mean new-prefill tokens | 2372.34 | 1637.55 | -30.97% |
| SLO-compliant goodput | 0.8336 req/s | 0.9911 req/s | +18.90% |
| Completion | 100% | 100% | equal |

The result passes every paper gate: 3/5 families receive a non-raw frozen
level, certificate coverage is 50%, certified prefix physical reuse is
99.9638%, dynamic-suffix reuse is zero, scope-invalid admission is zero, and
policy-attributable quality violations are zero. It does not pass the stronger
gate because only 3/5 families qualify, mean TTFT reduction is below 30%, and
new-prefill reduction is below 35%.

## Prospective protocol

The final run uses a source-group-disjoint split drawn from the 1,300-row full
pool:

- development: 25 sessions, five per family, ten turns each;
- sealed held-out: 50 sessions, ten per family, ten turns each;
- held-out workload: 450 future requests per repeat and three fresh processes;
- overlap with prior samples and source groups: zero;
- model/runtime: Llama-3.1-8B-Instruct, FP16, vLLM, one RTX 3090 per cell,
  concurrency 2, 16K maximum model length, 96 output tokens.

The compiler never branches on dataset or task name. It splits stable text into
16 contiguous, character-preserving units and applies the same ladder to every
task: L0=raw, L1=25%, L2=75%, and L3=100% stable-prefix promotion. Development
selects the highest-prefix-gain level satisfying completion, quality, scope,
length-stop, physical-reuse, and dynamic-suffix gates.

The frozen family table is:

```json
{
  "LongBench:hotpotqa": "L2",
  "LongBench:narrativeqa": "L2",
  "LongBench:qasper": "L0",
  "RULER:niah_single_1": "L3",
  "RepoBench:python_v1.1": "L0"
}
```

At Turn 0, a session may use only levels that its family qualified on
development. Strict teacher-forced verification attempts the frozen maximum,
then descends through eligible levels, and finally fails closed to L0. This is
certificate-guided level descent, not a task-specific exception.

## Family results

| Family | Frozen | Certificate coverage | Mean TTFT delta | New-prefill delta | Quality violations |
| --- | ---: | ---: | ---: | ---: | ---: |
| HotpotQA | L2 | 90% | -64.57% | -67.52% | 0 |
| NarrativeQA | L2 | 60% | -36.56% | -38.03% | 0 |
| Qasper | L0 | 0% | +0.22% | 0% | 0 |
| RULER | L3 | 100% | -87.52% | -97.06% | 0 |
| RepoBench | L0 | 0% | -0.80% | 0% | 0 |

Within prospectively qualified families, including their per-session raw
fallbacks, mean TTFT falls by 57.75%, p95 TTFT by 21.22%, new-prefill work by
62.23%, and SLO goodput increases by 60.96%. These subset metrics are an
analysis of qualified scope, not a replacement for the all-family global row.

The final runtime choices are deterministic across all three repeats: HotpotQA
uses L2 for 9/10 sessions; NarrativeQA uses L2 for 5/10, descends to L1 for
1/10, and falls back to L0 for 4/10; RULER uses L3 for 10/10. Qasper and
RepoBench remain L0 for all sessions.

## Quality and attribution

All 1,350 held-out future request pairs complete. There is one score difference
above 0.03 across the three repeats, but it occurs on an effective-L0 raw
fallback pair. It is therefore reported as fresh-process raw-vs-raw variation,
not attributed to ContractKV. No request admitted under L1-L3 has a quality
violation, and no dynamic suffix token is reused.

This attribution split fixes an earlier analysis error that counted a raw
fallback pair difference as a ContractKV layout violation. The broad difference
is retained in the CSV rather than discarded.

## Root-cause closure

The earlier Llama difficulty was not one single failure:

1. **Code/granularity issue.** Four stable pieces made nominally small ladder
   levels collapse onto the same 25% boundary. Sixteen character-preserving
   pieces make the ladder real.
2. **Analysis issue.** Effective-L0 cross-process differences were incorrectly
   attributed to ContractKV. The final schema separates broad pair differences
   from policy-attributable violations.
3. **Runtime capacity issue.** The R1 98% completion rate came from one
   RepoBench session producing HTTP 400 on both raw and ContractKV at 8K. The
   fair 16K configuration completes every request for both policies.
4. **Design issue.** A single family level was too brittle. Certificate-guided
   descent preserves the prospective family policy while adapting safely at
   session granularity.
5. **Real model/task boundary.** Qasper development outputs violate quality at
   all tested levels in R3, while RepoBench fails strict verification. They must
   remain raw on Llama. This is evidence for fail-closed control, not a code bug.

The defensible claim is therefore: **ContractKV generalizes successfully to
Llama under a prospectively qualified adaptive layout policy.** It is not a
claim that every Llama task is reorderable or that p95 TTFT improves globally.

## Evidence

- `results/cross_model/llama_broad_generalization_r3/split_commitment_v0.json`
- `results/cross_model/llama_broad_generalization_r3/llama_broad_qualification_v0.json`
- `results/cross_model/llama_broad_generalization_r3/development_layout_summary_v0.csv`
- `results/cross_model/llama_broad_generalization_r3/heldout_scope_aggregate_v0.csv`
- `results/cross_model/llama_broad_generalization_r3/heldout_scope_repeats_v0.csv`
- `results/cross_model/llama_broad_generalization_r3/heldout_level_selection_v0.csv`
- `results/cross_model/llama_broad_generalization_r3/heldout_quality_v0.csv`
- `results/cross_model/llama_broad_generalization_r3/heldout_gate_v0.json`

Raw request and prefix-metric JSONL files remain on the 8T server volume under
`results/cross_model/llama_broad_generalization_r3/repeat*/`; they are excluded
from Git by design.

## Result-producing code

- `scripts/phase22_llama_layout_ladder.py`
- `scripts/phase22_llama_broad_live.py`
- `scripts/phase22_llama_broad_analysis.py`
- `scripts/phase22r_prepare_llama_split.py`
- `scripts/run_phase22r_llama_broad.sh`
- existing serving helpers: `scripts/run_vllm_server.sh`,
  `scripts/stop_vllm_server.sh`, `scripts/phase19b_end_to_end_live.py`,
  `scripts/phase20a_official_quality.py`,
  `scripts/install_vllm_v1_ephemeral_shadow_hook.py`, and
  `scripts/install_vllm_v1_prefix_metrics_probe.py`.
