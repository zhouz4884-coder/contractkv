# Phase 26C: Transactional Tier-B Control Plane

## Implementation

The Phase 26 control plane implements a two-gate transaction:

`Tier E -> BenefitGate -> isolated candidate free decode -> typed SafetyGate -> promotion or abort`

Candidate generations use unique cache-salt namespaces. Before measured future requests, the server cache is reset and only the selected layout is promoted. This prevents candidate namespaces from being consumed by the measured path. Promotion cost is included with verifier cost and any portion beyond the frozen tool-slack budget is charged to net TTFT.

The typed contract stubs are deterministic and reference-free. A process-isolated fault harness enforces a deadline and covers PASS, FAIL, UNKNOWN, malformed output, timeout, contract exception, frontend disconnect, benefit rejection, duplicate request, and code-structural PASS. The transaction is idempotent by `txn_id`; every abort releases ephemeral control-plane state and publishes zero entries.

## Fault Matrix

The 10-case matrix produced three commits and seven aborts. All checks passed:

- FAIL/UNKNOWN/timeout/exception/disconnect published zero entries.
- A safety PASS with negative expected benefit aborted.
- Duplicate finalization was idempotent and added zero entries.
- No transaction metadata or ephemeral allocation remained after a terminal state.
- Dynamic-suffix reuse was fixed at zero in the controller and is independently checked from live vLLM telemetry in Phase 26D.

## Important Boundary

The typed contract and transaction coordinator are Python control-plane code. Candidate block publication is implemented conservatively as isolated namespace, reset, and selected-layout re-prefill; Phase 26 does not claim zero-copy promotion of typed candidate KV blocks. The repository's earlier source-level PSTP probes establish vLLM commit/abort and scheduler microchunk mechanisms, but the new typed stub is not executed inside a CUDA kernel or vLLM block manager.

This boundary matters: Phase 26 tests whether hierarchical behavioral certification can safely recover deployable scope and net serving benefit. It does not present a new in-kernel verifier.
