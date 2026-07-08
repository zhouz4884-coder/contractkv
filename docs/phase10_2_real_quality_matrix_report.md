# Phase 10.2 Real Quality Matrix Report

## Goal

Replace the Phase 4 proxy quality-risk ledger with real Qwen3-8B model outputs for the existing unified samples.

## Setup

Model server:

```text
model: Qwen3-8B
served-model-name: qwen3-8b
backend: vLLM 0.10.2 OpenAI API
max_model_len: 32768
max_num_seqs: 1
dtype: float16
gpu: 1 x RTX 3090
```

Runner:

```text
scripts/run_real_quality_matrix.py
```

Outputs:

```text
results/hard_systems/real_quality_outputs_qwen3_8b_v0.jsonl
results/hard_systems/real_quality_matrix_qwen3_8b_v0.csv
```

The first run used `max_tokens=64` and exposed Qwen3 thinking-token truncation. The final v0 run added `/no_think`, requested the shortest answer only, and used `max_tokens=128`.

## Data

Input samples:

```text
RULER: 20
LongBench: 100
RepoBench: 20
Total: 140
```

Conditions:

```text
full_context_baseline
segment_eviction
context_truncation
boundary_corruption
boundary_repair
contractkv_safe_decision
```

Total attempted real model requests:

```text
140 samples x 6 conditions = 840
```

Observed status:

```text
successful requests: 816
HTTP 400 context-overflow requests: 24
```

The 24 HTTP errors are concentrated in LongBench `narrativeqa` and are real vLLM context-limit failures. The server log reports requests above the 32768-token maximum, for example 46781, 36373, and 32964 input tokens.

## Aggregate Results

Dataset-level mean scores:

| Dataset | Baseline | Eviction | Truncation | Boundary Corruption | Boundary Repair | ContractKV Safe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RULER | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| LongBench | 0.2741 | 0.1386 | 0.1391 | 0.2651 | 0.2614 | 0.2740 |
| RepoBench | 0.2321 | 0.0779 | 0.0931 | 0.2327 | 0.2881 | 0.1932 |

Key task-level drops:

```text
RULER segment_eviction: quality_drop = 1.0000
LongBench hotpotqa segment_eviction: quality_drop = 0.5114
LongBench hotpotqa context_truncation: quality_drop = 0.4630
LongBench qasper segment_eviction: quality_drop = 0.1651
RepoBench segment_eviction: quality_drop = 0.1541
RepoBench context_truncation: quality_drop = 0.1390
```

Boundary corruption and repair were less damaging than eviction/truncation in this v0 prompt construction. RepoBench boundary repair even improved the proxy similarity score relative to baseline, which should be treated as a prompt/scoring artifact until verified with official RepoBench scoring.

## What This Proves

1. The quality matrix is now based on real Qwen3-8B outputs, not only proxy heuristics.
2. Segment eviction produces strong real degradation on RULER, LongBench hotpotqa, qasper, and RepoBench.
3. Context truncation also causes real degradation on LongBench and RepoBench.
4. The ContractKV-safe text-level decision condition mostly preserves baseline quality on RULER and LongBench, with a RepoBench drop that needs further scoring refinement.
5. vLLM 32K context overflow is a real hard-system boundary for a subset of LongBench narrativeqa samples.

## What This Does Not Prove

This phase still does not prove:

```text
real KV block movement
real KV cache memory saving
segment-level vLLM block placement
official LongBench or RepoBench benchmark scores
```

The scores are real model-output scores under the Phase 10.2 prompt conditions, not official benchmark submissions.

## Risk(s, a) Replacement

For Phase 10 onward, `results/hard_systems/real_quality_matrix_qwen3_8b_v0.csv` should be treated as the v0 real quality-risk source:

```text
Risk(dataset, task, condition) = mean_quality_drop
```

The old Phase 4 proxy ledger remains useful only as design characterization.
