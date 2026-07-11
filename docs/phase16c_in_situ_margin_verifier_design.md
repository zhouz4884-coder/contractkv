# Phase 16C In-Situ Margin Verifier

## Goal

Phase 16C is the planned replacement for the external teacher-forced SLC v2
pipeline. The design moves verification closer to the serving path:

- capture raw output token IDs and raw margins when the raw request is generated
- run candidate verification as a special request mode
- compare every answer position under teacher forcing
- require top-1 match, stop consistency, absolute margin, and relative margin
  degradation bounds
- abort early and roll back the ephemeral transaction on failure

## Current Evidence From SLC v2

The current valid implementation is still external teacher-forced verification.
It already establishes the need for an in-situ verifier:

- 734 candidates
- certificate issue rate: 66.08%
- unsafe rejection rate: 94.12%
- retained certified prefix gain: 64.40%
- two held-out false-safe cases remain

Those two false-safe cases motivate adding raw/candidate margin consistency and
backend-aligned verification. However, Phase 16C is not implemented as a vLLM
request mode yet.

## Required Request Fields

```text
request.mode = contractkv_verify
request.reference_answer_ids
request.reference_raw_margins
request.stable_prefix_end_token
request.shadow_txn_id
```

## Certificate Conditions

For every answer token position:

```text
candidate_top1 == raw_answer_token
candidate_margin >= tau_abs
raw_margin - candidate_margin <= tau_drop
```

The verifier must also check stop token/sequence consistency, answer length,
dependency edges, and output contract compatibility.

## Boundary

This document is a design and integration target. It should not be cited as a
new measured result beyond the existing SLC v2 evidence in
`docs/phase15d_task_bearing_certification_report.md`.

## Artifacts

- `scripts/phase14slc_teacher_forced_verify.py`
- `results/end_to_end/phase15_slc_teacher_forced_summary_v2.csv`
