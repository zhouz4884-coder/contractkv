# Phase 17 Closeout: Verification-Driven Transactional Promotion

## What Completed

Phase 17 integrates the previously independent verifier, prefix-promotion transaction, and quiescence mechanisms in a real vLLM V1 scheduler path.

1. A pre-cleanup EngineCore hook derives `VerifyReport` from real prompt-logprob tensors.
2. `PASS` permits block-aligned promotion and a post-commit certificate; `FAIL`, `INCOMPLETE`, `CANCELLED`, and `PENDING` abort.
3. Concurrent and injected-fault executions preserve transaction isolation and prevent aborted promotion.
4. Live verifier work stays quiescent under foreground load with a 6.87 ms p95 penalty.
5. Fresh Qwen3-8B calibration was rerun after correcting the terminal-token protocol.

## Code Versus Idea Diagnosis

The Phase 17 bottleneck was primarily **code/protocol**, not the control-plane idea. vLLM returns EOS in a stopped completion's token-ID sequence. Including it as an answer token and then appending another EOS shifted the stop check and created artificial incompleteness. The repaired one-terminal-token protocol restores meaningful verifier coverage.

The idea nevertheless has a genuine remaining limitation: exact-token/logprob attestation does not reject every held-out semantic quality loss. Two of 17 held-out unsafe candidates passed the frozen intrinsic gates. This is a verifier-strength limitation, not a reason to weaken fail-closed execution or tune thresholds on held-out labels.

## Claims and Non-Claims

Supported:

* ContractKV can perform verification-driven transactional prefix promotion inside the vLLM V1 scheduler.
* Promotion is certificate-gated, deduplicated for shared stable content, and fail-closed on tested terminal/fault paths.
* Shadow verification can run without material foreground interference in the tested compact workload.

Not supported yet:

* A production-quality safety bound below 3%.
* Task-bearing quality preservation for all promoted requests.
* A throughput or latency acceleration claim from the verifier itself.

The next research task is a task-semantic verification signal or an eligibility contract that rejects the two observed held-out failure modes without selecting thresholds on held-out outcomes.
