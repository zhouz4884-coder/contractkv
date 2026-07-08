# Phase 10.5B Anchored Recompute Actuator Report

## Goal

Upgrade the Phase 10.4B full sequence/group recompute actuator into a prefix-anchored suffix recompute POC:

```text
retain prefix physical blocks
free suffix physical blocks
set request.num_computed_tokens = anchor_token_end
resume request through vLLM
```

This is the first real RAR actuator proof.

## Implementation

Installer:

```text
scripts/install_vllm_v1_anchor_recompute_probe.py
```

Summary builder:

```text
scripts/build_anchor_recompute_probe_summary.py
```

Runtime guard:

```text
CONTRACTKV_ANCHOR_RECOMPUTE_PROBE=1
CONTRACTKV_ANCHOR_TOKEN_END=1024
CONTRACTKV_BOUNDARY_GUARD_TOKENS=32
```

The probe is inactive unless the guard is set.

## Required Runtime Invariants

Success requires all of:

```text
prefix_blocks_retained_exact == true
suffix_blocks_freed_exact == true
free_gpu_blocks_delta >= suffix_blocks_freed
num_computed_tokens_after == anchor_token_end
request_completed == true
response non-empty
duplicate_block_id_detected == false
block_table_consistency == true
```

These invariants distinguish RAR from full recompute.

## Outputs

```text
results/hard_systems/anchored_recompute_events_v0.jsonl
results/hard_systems/anchored_recompute_poc_v0.csv
```

## Results

| Model | Anchor Token | Guard Tokens | Prefix Retained | Suffix Freed | Free Block Delta | Completed | Success |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Qwen3-4B | 1024 | 32 | 64 | 64 | 64 | true | true |
| Qwen3-8B | 1024 | 32 | 64 | 64 | 64 | true | true |

Both models passed:

```text
prefix_blocks_retained_exact = true
suffix_blocks_freed_exact = true
num_computed_tokens_after = 1024
```

## Interpretation

ContractKV now has a real vLLM V1 RAR primitive:

```text
anchor-resident prefix + suffix KV release + anchored recompute
```

This is stronger than Phase 10.4B full recompute because the retained prefix physical block IDs remain in the request block table while suffix blocks return to the block pool.

## Boundary

This is still a POC, not a pressure benchmark. It proves the actuator can work for one request on Qwen3-4B and Qwen3-8B. It does not yet prove improved completion, block headroom under workload pressure, SLO goodput, or quality preservation under policy comparison.

## Decision

Proceed to Phase 10.5C pressure policy evaluation.
