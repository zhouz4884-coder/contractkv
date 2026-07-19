# TSC Service-Evaluation Extension

## Decision

Overall gate: **PASS**.

## Headline: Authorized Service Locality

The primary service result is the prospectively frozen shared-template scope. Tenant-private observations, request IDs, arrival order, server process, and cache namespace remain isolated.

| Model | Tenants/template | Load | Mean TTFT reduction | p99 reduction | New-prefill reduction | 500-ms SLO goodput |
|---|---:|---:|---:|---:|---:|---:|
| mistral | 25 | 80% | 54.35% | 29.65% | 50.75% | 4.48x |
| qwen | 25 | 80% | 92.62% | 95.78% | 98.15% | 4.81x |

## Working-Set Boundary

| Active templates | Arrival order | Reuse distance | New-prefill reduction | Mean TTFT reduction | 1500-ms SLO goodput |
|---:|---|---:|---:|---:|---:|
| 5 | round_robin | 5.0 | 98.15% | 93.69% | 1.15x |
| 5 | zipf | 5.0 | 98.26% | 94.26% | 1.21x |
| 25 | round_robin | 25.0 | -0.00% | 0.36% | 1.00x |
| 25 | zipf | 22.7 | 83.18% | 84.63% | 1.19x |
| 50 | round_robin | 50.0 | 0.00% | 0.64% | 0.99x |
| 50 | zipf | 37.5 | 69.14% | 73.40% | 1.22x |

## Multi-Tenant Consolidation

| Scope | Policy | Mean TTFT (ms) | p95 TTFT (ms) | SLO req/s | Peak used blocks | Minimum free blocks | Jain fairness |
|---|---|---:|---:|---:|---:|---:|---:|
| 40 tenants / 100% authorized | D0-native-apc | 1364.5 | 1950.5 | 1.064 | 530.0 | 1856.0 | 0.6663 |
| 40 tenants / 100% authorized | D2-full-contractkv | 90.8 | 122.7 | 10.984 | 149.0 | 2237.0 | 1.0000 |
| 80-tenant density | D0-native-apc | 1219.9 | 1933.0 | 1.152 | 530.0 | 1856.0 | 0.7142 |
| 80-tenant density | D2-full-contractkv | 90.0 | 119.6 | 11.033 | 149.0 | 2237.0 | 1.0000 |

## Natural Mixed-Trace Boundary

When every session has effectively unique stable content, ContractKV has no service-template reuse opportunity; the exact-path verification and isolated namespace add measurable overhead. This negative control defines when the mechanism should not be enabled.

| Model | Load | D2/D0 SLO-goodput | Mean TTFT reduction | p99 reduction | New-prefill reduction |
|---|---:|---:|---:|---:|---:|
| mistral | 80% | 0.94x | -3.03% | -3.29% | -2.55% |
| mistral | 100% | 0.91x | -4.69% | -5.05% | -2.58% |
| mistral | 120% | 0.83x | -8.69% | -7.48% | -2.59% |
| qwen | 60% | 0.95x | -2.36% | -2.43% | -1.63% |
| qwen | 80% | 0.93x | -1.67% | -3.98% | -1.63% |
| qwen | 100% | 0.91x | -2.37% | -4.14% | -1.63% |
| qwen | 120% | 0.87x | -4.26% | -7.20% | -1.63% |

## Safety and Economics Closure

Tenant aggregate rows: 34. Unauthorized cross-tenant reuse, dynamic suffix reuse, and scope-invalid admissions are all zero.

Positive live economics lanes: 71/84; certificate accepted: 82/84; rejected lanes execute measured raw-order fallback.

## Submission closure

P0-A real task-quality gate: **True** across 1350 paired future outputs. Four qualified templates fan out certificates; Qasper follows frozen raw fallback. P0-B certificate-granularity gate: **True**. Overall submission-closure gate: **True**.

## Service lifecycle

Lifecycle gate: **True** across 10 events.

## Claim boundary

Open-loop and tenant results are real vLLM serving measurements. P0-A uses frozen task metrics and task-specific output budgets, but is a five-template deployment-object audit rather than a full benchmark submission. The archived all-template negative control is retained and is not counted as a safe ContractKV admission. The lifecycle model/tokenizer events test routing scope without claiming an in-process weight reload.
