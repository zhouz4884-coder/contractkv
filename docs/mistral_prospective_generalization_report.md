# Mistral Prospective Generalization

## Purpose

Mistral-7B-Instruct-v0.3 is the final prospective extension model. It is not a post-hoc replacement for Llama: the runtime identity, split, development gate, heldout gate, verifier, and stop rule were frozen before the sealed heldout partition was opened.

## Protocol Audit

Ten development-only smoke cases checked exact rendered-prompt identity, forced-token offsets, deterministic termination, and decoded segment boundaries. Mistral's chat template legitimately contributes an empty extra generation suffix after `[/INST]`; the protocol accepts this only when exact prompt identity and offset checks pass. Typed segments use a frozen `\n\n` separator to avoid SentencePiece/BPE boundary-space ambiguity.

An initial 2,600-word RepoBench context exceeded the 8,192-token budget. The stable-context limit was frozen at 1,500 words before development; the maximum audited rendered prompt was 6,486 tokens. The final audit had 0 protocol bugs, 0 nondeterministic rows, and 0 length stops.

## Parser Compatibility Fix

Mistral can return two vocabulary IDs that decode to the same visible string in `top_logprobs`. The old parser removed every same-string item and falsely marked the stronger competitor unavailable. The corrected parser removes exactly one sampled token entry by decoded string and chosen log probability, retaining distinct same-text vocabulary competitors. This fix was made before the sealed heldout set was opened, and its source hash is part of the frozen policy manifest.

## Prospective Evaluation

The split contains five task families: RULER, LongBench hotpotqa, narrativeqa, qasper, and RepoBench. Development used 25 sessions and heldout used 50 disjoint sessions; every session had ten turns, yielding 225 and 450 future requests respectively.

### Development Gate

| Metric | Result |
|---|---:|
| Completion | 100% |
| Certified sessions | 10 / 25 (40%) |
| Unsafe certified sessions | 0 |
| Future quality violations in certified sessions | 0 |
| Maximum ContractKV quality drop | 0.00444 |

The preregistered development gate passed, so the sealed heldout partition was opened without threshold retuning.

### Sealed Heldout Gate

| Metric | Raw order | ContractKV | Change |
|---|---:|---:|---:|
| Completed requests | 450 / 450 | 450 / 450 | equal |
| Mean TTFT | 1096.75 ms | 688.97 ms | -37.18% before verifier accounting |
| Net mean TTFT | 1096.75 ms | 742.25 ms | **-32.32%** |
| p95 TTFT | 2192.67 ms | 2163.33 ms | -1.34% |
| Mean new-prefill tokens | 2603.40 | 1576.02 | **-39.46%** |
| Mean prefix-hit tokens | 101.12 | 1128.50 | +1016% relative |
| Safe certificate coverage | - | 25 / 50 (50%) | gate met |
| Certified stable-prefix reuse | - | 99.96% | gate met |
| Dynamic-suffix reuse | - | 0 tokens | gate met |
| Unsafe certified sessions | - | 0 | gate met |
| Maximum quality drop | 0 | 0.02 | within 0.03 budget |

All nine frozen heldout gates passed. Token-budget efficiency is the cross-model invariant: ContractKV avoids 1,027.38 mean prefill tokens per future request even though absolute milliseconds differ across models.

## Load Extension

The heldout input and frozen policy were replayed at concurrency 1 and 4 only after the main gate passed.

| Concurrency | Raw mean TTFT | ContractKV mean TTFT | Mean reduction | Raw p95 | ContractKV p95 |
|---:|---:|---:|---:|---:|---:|
| 1 | 644.70 ms | 413.70 ms | 35.83% | 1239.71 ms | 1247.45 ms |
| 4 | 1725.47 ms | 1096.43 ms | 36.46% | 4032.99 ms | 3179.88 ms |

At concurrency 1 the mean and total wall time improve, while p95 is 7.74 ms worse; this small tail regression is retained rather than hidden. At concurrency 4 both mean and p95 improve. New-prefill reduction remains 39.46% at both loads.

## Claim Boundary

This experiment establishes a second positive model under prospective gates. It does not prove universal behavior across all decoder architectures, nor does it make Llama's stale certificate valid. ContractKV generalizes as a model-agnostic transactional substrate paired with model/task/observation-scoped behavioral certification and fail-closed raw-order fallback.
