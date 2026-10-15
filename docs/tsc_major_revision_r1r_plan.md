# R1R: Query-Bound, Prefix-Assisted Reattestation

The original R1 matrix remains immutable. Its new-query counterexamples and
complete verification costs are evidence, not data to tune away. This repair
study addresses the user's updated objective: find an implemented, measured
solution rather than only explain weak results.

## Root Causes and Proposed Repairs

1. A Turn-0 path witness was reused after query text changed. Bind a certificate
   to the exact query text, system/renderer identity, generation configuration,
   layout and stable content. A new query is initially served in raw order;
   it must obtain its own strict raw-reference witness before compiled reuse.
2. That raw business output can itself be the reference. Do not generate a
   duplicate raw answer merely to certify the next occurrence of that query.
3. vLLM disables all prefix reuse for generic prompt-logprob requests. An
   internal verifier only needs answer/stop rows. Permit a read-only lease on
   a matching, previously approved stable prefix, with a block-aligned guard.
   All answer/stop rows remain computed. Generic prompt-logprob requests retain
   their original behavior. Rejected shadow work still publishes zero new blocks.
4. Test uniform allowed-level descent rather than confuse the R1 maximum-only
   diagnostic with the original adaptive policy. No level is selected using
   sealed held-out quality results.

## Prefix-Read Safety Invariants

- The engine records approved block-hash chains only after successful strict
  verification and actual stable-prefix commit.
- A read must match the request's cache namespace, policy identity and exact
  block-hash chain. Mere client metadata does not create an approved prefix.
- The read boundary is no later than the stable-only boundary minus one full
  block and strictly before the first required answer-logprob row.
- Native cache lookup still verifies residency and exact token-prefix matching.
  Evicted entries fall back to shorter/zero physical hits, never fabricated hits.
- Missing answer or stop rows abort. All candidate suffix allocations remain
  ephemeral until PASS, including when an approved prefix is borrowed.
- Failure releases the borrowed lease; it does not revoke or mutate already
  approved immutable prefix state. It inserts no new candidate hashes.

## Development and Sealed Validation

Use a source-disjoint development cohort for implementation/correctness and
cost calibration. Exclude original R1 cohorts and archived development groups.
Use all five task families. Freeze the final client, backend patch, query schema,
budget, allowed layouts, cost gate and source-session commitment before opening
a new held-out cohort. Prior R1 failures are diagnostic inputs, not new held-out
successes.

Compare raw, query-bound full verification, and query-bound approved-prefix-read
verification. Keep model weights, dtype, concurrency, contexts, output budgets
and arrival rules matched. Report every raw fallback and first-use raw business
request; do not count only optimized occurrences.

The client must record actual business TTFT, full readiness-to-first-token delay,
wall-clock goodput, exact output IDs/scores, query-scope misses, complete verifier
cost, actual prefix-read tokens, cache-read eligibility and all publication events.
No tool-slack cost is subtracted from an observed clock. An overlap claim requires
real overlapping execution.

Primary targets are query-scope safety, zero rejected publication and a measured
reduction in verifier prefill/cost. Good end-to-end numbers are desired outcomes,
not guaranteed by the plan. If a cached-prefix path changes a decision, diagnose
row offsets, finite precision and scope identity before accepting it.

## Prospective validation frozen on 2026-10-15

The user's seven original revision requirements remain the complete scope. R1R
adds an implemented repair and a new validation cohort to the completed R1
evidence; it does not replace the earlier matrix or remove its counterexamples.
The newly supplied decision letter is byte-identical to the original local
letter (SHA256 e5b12656164650d7d9d13fd9377ded67b346b7963d5893735d84354173fea03d).

Development identified three cost improvements: use the first real raw business
output as a witness, read only a previously approved stable prefix, and extract
only required answer/EOS logprob rows. Transformer/KV computation remains real.
The final scheduler uses the actual supported CHUNK_TOKENS=128 and
ROUND_TOKENS=128. The earlier unused QUANTUM setting is retained as a failed
configuration attempt, not credited with a speedup.

Before any new validation outcomes, the client, backend, protocol, source inputs
and selected template cohort were frozen in validation/freeze_v1.json. Three
models and three fresh process repeats run:

| Study | Inputs | Policies | Cells | Future generations |
|---|---|---|---:|---:|
| Single session | 50 sealed sources, ten per family, one tenant | raw / full query attestation / prefix-assisted query attestation | 27 | 12,150 |
| Template reuse | First two committed sources per family, ten tenants per template | raw / prefix-assisted query attestation | 18 | 16,200 |

The template subset is selected by the committed source order, never quality or
latency. The two studies overlap in source identity, so they must not be pooled
as independent evidence. Policies rotate across repeats; cells use fresh server
processes and alternate GPU assignment. Every cell runs seven separate control
cases before the measured business interval. These control requests do not count
as business futures and cannot share a business prefix namespace.

Desired outcomes are fewer compiled-route quality drops, zero scope-invalid
admission/rejected publication, lower verifier cost and positive measured
full-cost service benefit. Failure of any desired outcome requires a diagnosis
and explicit reporting; it does not authorize changing this held-out protocol.
Request-level averages, tails, source clusters, raw-repeat variability, fallback
and first-use raw costs are all retained. No production prevalence or arbitrary
tool-observation safety is inferred from this metadata-only controlled suffix.

## Implemented variant and audit clarification

The final frozen repair compares rank-one answer/EOS checks with uniform descent
within the inherited family maximum. Auxiliary candidate-margin/degradation
bounds are wide (-1e9/+1e9), and this controlled repair study does not execute
the original submitted policy's profitability gate. `query-full` describes the
full-context verification computation, not all guards in the published policy.
The measurements cannot silently replace that policy's original main table.

Per-request output IDs and actual prompt counts are archived; complete prompt
token IDs/hashes are not separately logged in R1R. Input-repeat identity is
therefore supported by the committed source/session/turn, deterministic renderer
and model/configuration records. The report retains compiled failures even when
raw repeats vary, and distinguishes a witness match from a universal future
behavior guarantee.
