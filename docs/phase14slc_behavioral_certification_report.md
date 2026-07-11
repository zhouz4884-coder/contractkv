# Phase 14SLC Behavioral Certification

## Status

This report is retained for chronology, but the Phase 14SLC numbers are
superseded by Phase 15D SLC v2. Do not cite the original Phase 14SLC v0/v1
coverage or rejection rates as paper evidence.

Phase 15 fixed three issues:

- prompt identity mismatch in the stable-context construction
- truncated-logit indexing in teacher-forced verification
- fail-closed handling for EOS/explicit stop and length mismatch

The valid current evidence is documented in
`docs/phase15d_task_bearing_certification_report.md`.

## Current Valid SLC v2 Result

Across 734 candidates, SLC v2 issues certificates for 485 candidates
(66.08%), rejects 32 of 34 known unsafe candidates (94.12%), certifies 483 of
700 safe candidates (69.0%), and retains 64.40% prefix gain among certified
candidates.

Two held-out false-safe cases remain, so the correct claim is:

SLC is a useful fail-closed behavioral guard with high unsafe rejection and
paper-useful coverage, but it is not a formal semantic-equivalence proof and
must still be paired with task-bearing future replay.

## Artifacts

- `docs/phase15d_task_bearing_certification_report.md`
- `results/end_to_end/phase15_slc_teacher_forced_v2.jsonl`
- `results/end_to_end/phase15_slc_teacher_forced_summary_v2.csv`
- `scripts/phase14slc_teacher_forced_verify.py`
