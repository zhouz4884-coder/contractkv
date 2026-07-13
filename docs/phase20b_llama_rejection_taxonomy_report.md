# Phase 20B: Llama Rejection Taxonomy

## Method

Ten previously rejected-safe Llama sessions were replay-audited with deterministic task contracts. The audit distinguishes protocol defects, benign formatting differences, length/capacity stops, and genuine token-path divergence. No fuzzy F1 acceptance was introduced.

## Result

| Category | Sessions |
| --- | ---: |
| True token-path divergence | 5 |
| Length stop | 4 |
| Task-equivalent format divergence | 1 |
| Protocol bug | 0 |
| Nondeterministic replay | 0 |

The one task-equivalent case was recovered by structurally removing a leading bracketed control echo before exact scoring. Length-limited generations remain failures of the configured protocol budget rather than model-answer errors.

## Diagnosis

The rejection pattern is mostly model-specific path sensitivity, not a broken hook. One case was an evaluator normalization issue, and four cases expose output-length/protocol capacity. This evidence does not justify weakening the exact contract or declaring Llama generalization successful.
