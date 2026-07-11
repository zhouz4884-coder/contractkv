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

## Same-Backend Minimal Probe

Phase 16E adds a minimal Qwen3-4B probe through the same vLLM 0.10.2 Chat API.
For each case it generates a raw answer, appends that answer to a candidate
layout, requests `prompt_logprobs=2`, and checks the rank of every answer token.

Across 12 marker cases:

- raw generation success: 12 / 12
- prompt-logprob verification success: 12 / 12
- answer tokens checked: 146
- candidate top-1 matches: 146 / 146
- minimum top1-vs-runner-up margin: 8.56 logprob units

This closes the narrow same-backend top-1 smoke target. It also confirms that
the answer slice is non-empty; the result is not an empty-slice pass.

## Existing Evidence From SLC v2

The current valid implementation is still external teacher-forced verification.
It already establishes the need for an in-situ verifier:

- 734 candidates
- certificate issue rate: 66.08%
- unsafe rejection rate: 94.12%
- retained certified prefix gain: 64.40%
- two held-out false-safe cases remain

Those two false-safe cases motivate adding raw/candidate margin consistency and
backend-aligned verification. The dedicated scheduler-internal verifier request
mode is still not implemented.

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

The new result is a real same-vLLM-backend teacher-forcing smoke, but it uses
marker cases and does not yet check EOS/stop consistency, absolute deployment
thresholds on real tasks, early abort, or atomic commit-after-verification. The
734-candidate SLC v2 remains the broader quality evidence.

## Artifacts

- `scripts/phase14slc_teacher_forced_verify.py`
- `scripts/phase16c_vllm_teacher_forced_probe.py`
- `results/end_to_end/phase15_slc_teacher_forced_summary_v2.csv`
- `results/hard_systems/phase16c_vllm_teacher_forced_probe_v0.csv`
