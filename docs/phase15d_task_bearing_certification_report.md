# Phase 15D Task-Bearing Certified CAPOSC

## Goal

Phase 15D closes the quality guard gap for CAPOSC. The central question is not
whether a layout can be faster in isolation, but whether a certificate can
protect task behavior when the system deploys cache-friendly layouts.

## SLC v2 Teacher-Forced Certification

The valid SLC run uses prompt-identity checks, corrected truncated-logit
indexing, and fail-closed handling for EOS/explicit stop and length mismatch.
The earlier v1 result is not cited because its stable-context construction did
not match the intended prompt identity.

Across 734 candidates:

- certificates issued: 485 / 734 = 66.08%
- unsafe candidates: 34
- unsafe rejected: 32 / 34 = 94.12%
- safe certified: 483 / 700 = 69.0%
- retained prefix gain among certified candidates: 64.40%
- mean verification time: 1,410 ms
- p95 verification time: 2,829 ms

Two held-out false-safe cases remain:

- `qasper` sample 58, quality drop 0.031358
- `narrativeqa` sample 165, quality drop 0.050420

The token-path gate is therefore useful but not complete. The paper should state
that SLC is a high-precision guard with known residual risk, not a formal proof
of semantic equivalence.

## Task-Bearing Future Replay

The live Qwen3-8B replay uses 60 untouched sessions: 20 LongBench qasper, 20
RULER, and 20 RepoBench sessions. Each session has six turns. The system issues
a canary certificate on turn zero, then deploys or revokes it over future turns.

| Metric | Value |
| --- | ---: |
| sessions | 60 |
| future pairs | 205 |
| certificate issue rate | 68.33% |
| future mismatch rate | 0.49% |
| Wilson 95% upper bound | 2.71% |
| certificate revocations | 1 |
| mean quality drop | 0.000608 |
| max quality drop | 0.124626 |
| warm raw mean TTFT | 874 ms |
| warm deployed mean TTFT | 425 ms |
| warm TTFT reduction | 51.39% |
| warm new-prefill reduction | 55.60% |
| violated dependency edges | 0 |

The single future mismatch is a LongBench qasper case. The certificate is
revoked and subsequent turns fall back to raw order. RULER and RepoBench have no
future mismatches in this replay.

## Active-Tenant Interference

A separate Qwen3-8B live probe measures whether shadow/canary work interferes
with short active requests. Across three seeds:

| Condition | Active mean TTFT | Active p95 TTFT | Active mean latency | Active p95 latency |
| --- | ---: | ---: | ---: | ---: |
| baseline | 59 ms | 65 ms | 372 ms | 380 ms |
| shadow interference | 212 ms | 650 ms | 541 ms | 954 ms |
| penalty | +153 ms | +585 ms | +168 ms | +574 ms |

This is an important negative boundary: shadow canary work is not free when it
runs on the active serving GPU without a scheduling budget. Phase 15D therefore
supports certified layout deployment, but the canary/verification path must be
scheduled under slack, isolated on spare capacity, or rate-limited.

## Boundary

The replay uses task sanity checks and output contracts, not official full
benchmark scoring. The canary runs through the same live vLLM endpoint, but the
teacher-forced verifier is still an external process rather than an in-vLLM
certifier. The 2 s slack target hides 80% of canary cost; 100 ms and 500 ms
slack targets do not hide it in this run.

## Artifacts

- `results/end_to_end/phase15_slc_teacher_forced_v2.jsonl`
- `results/end_to_end/phase15_slc_teacher_forced_summary_v2.csv`
- `results/end_to_end/phase15d_task_bearing_raw_v0.csv`
- `results/end_to_end/phase15d_task_bearing_summary_v0.csv`
- `results/end_to_end/phase15d_active_tenant_interference_raw_v0.csv`
- `results/end_to_end/phase15d_active_tenant_interference_summary_v0.csv`
- `scripts/phase14slc_teacher_forced_verify.py`
- `scripts/phase15d_task_bearing_certified_replay.py`
- `scripts/phase15d_active_tenant_interference.py`
