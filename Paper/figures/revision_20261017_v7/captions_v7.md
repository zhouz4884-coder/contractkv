# Figure captions — version 7

The individual PDF/SVG/PNG files contain compact graphics only. This document supplies separate LaTeX-ready caption drafts. Fig. 1 and manuscript source are unchanged.

## Fig. 2. Full-Cost Benefits of Query-Scoped KV Reuse

Full-cost benefits on six source-disjoint HotpotQA/RepoBench sources, three models and three paired process repetitions/model. The strict query-scoped raw-witness protocol uses faithful 16K inputs and zero tool slack. (a) Bars normalize aggregate full service throughput to raw over three process pairs; individual ratios and min-max are retained in the supporting tables. Service wall charges initial business, planning, successful/failed qualification and synchronous waits, scoring and logging. (b) ContractKV totals include business and certification prefill; annotations report net count reduction and added certification work. Counts are initial scheduler prompt-minus-hit observations per 600-business-request run. (c) Mean readiness TTFT uses the frozen two-request wave clock over future requests. Process means, source-cluster intervals and tail costs are retained in the supporting tables.

[PDF](fig2_full_cost_benefits.pdf) · [SVG](fig2_full_cost_benefits.svg) · [PNG](fig2_full_cost_benefits.png)

## Fig. 3. Qualified Coverage and Free-Running Fidelity

(a) Task-level compiled coverage; each cell contains 810 future pairs/model/family. Hatched RepoBench cells inherit a development-frozen L0 policy and are not GPU-certification failures. (b) The earlier 50-source audit and six-source faithful validation observed 0/2,442 and 0/1,296 compiled output-ID differences. The lower panel reports raw-positive scorer credit within the faithful compiled subset, not a common accuracy measure. (c) One logged Qwen3-8B/HotpotQA doc69 sequence: an actual t0 witness, PASS/COMMITTED reply reporting 888 candidate blocks, and a t3 answer with identical seven output IDs plus native prefix reuse. Exact records and line identities are supplied; a standalone BlockStored event is not claimed.

[PDF](fig3_coverage_and_fidelity.pdf) · [SVG](fig3_coverage_and_fidelity.svg) · [PNG](fig3_coverage_and_fidelity.png)

## Fig. 4. Transactional Enforcement and Certificate Amortization

(a) The fixed-layout deployment certificate-granularity ablation reduces calls from 125 to 5 per 1,125-future-request trace (25-fold) and unhidden cost from 25.05 to 3.24 ms/request (7.7-fold); three process repetitions, independent axes. (b) Live Qwen 8B and 14B TP2 probes each reject 10/10 harmful dependency-valid layouts. Zero promotion applies to rejected compiled candidate state; native raw fallback caching remains separate. (c) A distinct five-process same-engine comparison reports D1/D2 goodput of 1.472/1.428 req/s, giving 97.0% retained mean goodput with four D2 verifier calls/trace. Whiskers are process min-max, not confidence intervals or a non-inferiority guarantee.

[PDF](fig4_transaction_and_amortization.pdf) · [SVG](fig4_transaction_and_amortization.svg) · [PNG](fig4_transaction_and_amortization.png)

## Fig. 5. Service Goodput and Physical KV Savings

Distinct original deployment-template studies. (a) The open-arrival workload reports absolute 500-ms SLO goodput. At 80% load, native APC and ContractKV achieve 0.173/0.831 req/s: +0.658 req/s and a 4.81x measured-point ratio. (b) In the same 80-identity density cells, peak allocator-used blocks fall 530 to 149 (71.9%) and minimum free blocks rise 381 within a 2,386-block pool. Those density cells also report 1.152/11.033 req/s under class-specific 750/1,500/3,000-ms SLOs in wave replay. The two SLO protocols stay separate. Registered identities are not simultaneous GPU requests, and these data do not isolate headroom as the sole cause of throughput improvement.

[PDF](fig5_service_goodput_and_kv_savings.pdf) · [SVG](fig5_service_goodput_and_kv_savings.svg) · [PNG](fig5_service_goodput_and_kv_savings.png)

## Fig. 6. How Locality and Residency Shape KV Reuse

(a) In the frozen 40-identity sharing sweep, the pale band marks the observed 50-75% sharing interval across which mean TTFT benefit rises; it is not a universal threshold. The zero-sharing -3.2% point is retained. (b) Round-robin and Zipf patterns over 5, 25 and 50 templates expose sensitivity to reuse distance and hot-set skew. The axis measures net mean TTFT reduction, not a directly observed residency fraction. Prefix-hit statistics are supplied separately. These observations distinguish reuse qualification from continued physical availability of KV state; no new eviction timeline or policy is inferred from the curves.

[PDF](fig6_locality_and_residency.pdf) · [SVG](fig6_locality_and_residency.svg) · [PNG](fig6_locality_and_residency.png)
