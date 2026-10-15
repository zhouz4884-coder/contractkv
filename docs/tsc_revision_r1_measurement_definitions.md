# R1 Measurement and Guarantee Definitions

## Serving measurements

- Observed TTFT is request submission to the first streamed content token.
  TPOT uses actual completion-token count, not the number of SSE chunks.
- Actual output token IDs come from vLLM's `return_token_ids` response. Text
  retokenization is not used to infer equality or the first divergent position.
- Main paired cells contain 10-turn sessions. Turn 0 is setup; turns 1-9 are
  measured futures. All cells execute a business warm request. D2 additionally
  generates a raw reference and runs the in-engine teacher-forced verifier.
- Main wall time includes reference generation, token preparation, verification,
  business warming, request preparation, and future replay. Goodput uses that
  measured wall time. A smaller steady-state TTFT need not imply larger
  setup-inclusive goodput on a short session.
- Net mean TTFT additionally reports the measured residual registration cost
  `sum(max(registration_ms - slack_ms, 0)) / all_future_requests`. This is
  amortized accounting, not a measured per-request scheduling overlap or a
  claimed p99 transformation. Observed and accounted columns remain distinct.
- The zero-slack service experiment uses a frozen Poisson arrival trace. Its
  registration wall time is included in end-to-end goodput without subtraction.
  Request TTFT is measured from actual post-registration request submission;
  cold deployment delay is separately represented by registration wall time.
  Service prompts and their initial token boundaries are prepared before the
  declared registration/replay interval. That interval does not include server
  startup or this client preparation. The main session-cell wall clock does
  include in-cell prompt preparation. These two experiment boundaries must not
  be conflated into a universal all-lifecycle latency measure.

## Output and scope

The original output budgets are 128/128/256/256/384 by task family. The 512-token
condition generates new bound certificates; a short-budget certificate is not
silently reused under a changed generation configuration. Actual generated
lengths, length stops, and counts beyond 96 tokens must be reported. A 512-token
limit does not establish a 512-token checked path if the model stops earlier.

Strict raw-reference agreement includes the terminal stop token. A length-stop
reference is incomplete and cannot publish any candidate blocks. A certificate
can only publish full blocks within both the stable-only segment boundary and
the actual token LCP. An unchanged prefix of a private observation does not
authorize adding that observation to the certified shared prefix.

Later-prompt free-generation behavior is tested empirically. Report all requests,
admitted compiled requests, and raw fallback separately. Raw-vs-raw repeat
variation is retained; output text changes, token changes and material task-score
drops are different measurements. Zero-score raw examples remain in the global
denominator, with positive-raw-score diagnostics reported to expose floor effects.

The common HotpotQA experiment fixes L2 for all models, independent of observed
held-out outcomes. It is a controlled common-layout test with online attestation
and raw fallback, not a claim that every model attests every shared session.

The independent free-generation client tests one frozen maximum level per
model/family, then falls back to raw on rejection. It does not rerun the original
adaptive compiler's eligible-level descent or its net-benefit admission gate.
Its 1500-word context limit, generic task instruction and longer output budgets
also differ from some published all-workflow cells. These new robustness/cost
probes must not silently replace Table III's original end-to-end policy results.
The service experiment separately executes the existing cache-aware compiler.

The recorded `scope_invalid_admission` checks the fields implemented by the
runner (stable-prefix identity and generation budget), not arbitrary future
behavioral equivalence. The free-generation stress changes query wrappers;
Turn-0 path agreement does not certify those changes. Positive registration
and a valid prefix hash can therefore coexist with a later task-score drop.
R1 reports those drops without changing the frozen admission rules or relabelling
them as harmless. A stricter future-input binding needs prospective qualification
or reattestation and is not claimed as an evaluated repair in this batch.

Increasing the output cap does not force the model to produce a longer answer.
Positive admitted paths ending before 96 tokens must not be described as
512-token certified paths, even in the 512-budget condition. The extended cap
also exercises incomplete/length-stop rejection; these are different findings.

## Statistical interpretation

The fixed three-model macro CI estimates uncertainty in the average effect for
those models and source sessions. It is not the spread of model effects or a
prediction interval for new architectures. R1 resamples identical source sessions
jointly across models and fresh processes within each model. Model-level point
estimates and ranges are shown alongside the macro interval.

## Security and provenance

The original Qwen3-8B guard probe measured raw and candidate free outputs plus
the actual verifier decision; its effective score selected one of those prior
outputs according to the decision. A supplemental Qwen3-14B TP2 guard probe
adds a new real business generation after each decision, under the committed
candidate salt on PASS or raw messages on rejection. Its raw outputs are saved
separately, outside the completed main cell's count and timing interval. These
two evidence types must not be described interchangeably.

Hashing establishes byte identity, not confidentiality. Valid signatures establish
authorized issuer identity, not truthful semantic labelling. The registration
audit rejects declared private/mutable publication and untrusted issuer cases,
but deliberately shows that a trusted operator's mislabelled private segment is
not detectable from a valid hash/signature alone. Its CPU validator evidence is
not relabelled as a live confidentiality proof.

Authorization-domain cache separation does not eliminate timing inference within
an authorized shared-prefix domain. The prototype does not provide a timing-channel
defense, and raw native APC paths are not a general application security boundary.
The model-serving endpoint in the R1 run is bound to localhost and treated as an
operator-internal endpoint, behind any production-facing authentication gateway.

Archived template self-reference, archived incomplete timing, live raw-reference
attestation, and CPU state-machine stress retain distinct provenance labels.
Superseded startup/boundary attempts are quarantined, not silently removed.
