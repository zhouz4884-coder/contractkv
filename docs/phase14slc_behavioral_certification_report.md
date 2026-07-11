# Phase 14SLC Behavioral Certification

## SLC-A: Teacher-Forced Token-Path Certification

The verifier runs Qwen3-8B on GPU1 and checks every token of the raw greedy answer under the candidate prompt. A certificate requires every candidate top-1 token to equal the raw token, consistent stopping behavior, and a nonnegative minimum logit margin.

| Full paired pool metric | Result |
| --- | ---: |
| Candidate layouts | 734 |
| Known unsafe layouts | 34 |
| Unsafe layouts rejected | 33/34 (97.1%) |
| Safe layouts certified | 220/700 (31.4%) |
| Retained safe prefix gain | 20.4% |
| Mean verification time | 2.10 s |
| p95 verification time | 3.01 s |

This is a strong fail-closed safety filter, especially for RULER where it certifies all examples, but it does not meet the planned 60% safe coverage. It is therefore not used as the main performance selector.

## SLC-B: Epoch Transfer

On a separate six-session synthetic multi-turn split, all first-turn raw/CAPOSC outputs matched and all 30 K=5 future pairs also matched. Shadow runtime averaged about 355 ms, so 500 ms and 2 s tool slack hid every shadow in this small replay while 100 ms hid none.

The zero-failure Wilson upper bound remains 11.35% at only 30 future pairs. This demonstrates transfer behavior but is not sufficient for the 3% deployment safety target.

## Artifacts

- `scripts/phase14slc_teacher_forced_verify.py`
- `scripts/phase14slc_epoch_transfer.py`
- `results/hard_systems/phase14slc_teacher_forced_summary_v0.csv`
- `results/hard_systems/phase14slc_epoch_summary_v0.csv`
