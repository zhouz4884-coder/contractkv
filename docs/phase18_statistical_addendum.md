# Phase 18 Statistical Addendum

## Scope

This addendum changes only the Phase 18 summary schema and interpretation. It
does not rerun the experiment, modify raw measurements, or retune a threshold.
The previous closeout mixed a pooled p95 criterion with a worst-seed guard in
one `gate_pass` field. Those questions are now reported separately.

## Frozen Gates

| Gate | C3 compact + polling | C4 compact + parking |
| --- | --- | --- |
| Functional/lifecycle | PASS | PASS |
| Pooled systematic interference (<=10 ms) | PASS (-4.80 ms) | PASS (-3.37 ms) |
| Median paired-seed interference (<=10 ms) | FAIL (+13.17 ms) | PASS (-4.02 ms) |
| All-seed guard (<=10 ms) | FAIL (+58.39 ms) | FAIL (+20.30 ms) |

The negative pooled deltas are run-to-run variation and are not evidence that
verification accelerates foreground requests. The direct mechanism evidence is
the 2,147.96x reduction in verifier output bytes together with removal of the
previous systematic positive pooled residual.

## Frozen Conclusion

> Engineering closure passed; compact egress removes the systematic pooled
> residual. Per-seed tail determinism is not established under the saturated
> stress burst.

Parking remains a foreground-safe lifecycle mechanism, not a standalone
latency optimization. The current evidence does not trigger CUDA collision
instrumentation or a wall-time lookup table.
