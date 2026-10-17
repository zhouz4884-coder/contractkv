# ContractKV revision figure captions

Draft captions for the new figure files. Manuscript source and Fig. 1 are unchanged.

## Fig. 2. Strict Serving Performance

Three models are evaluated on the same six held-out HotpotQA/RepoBench sources with faithful 16K inputs, query-scoped raw-witness qualification, greedy decoding and zero tool slack. (a) Throughput is normalized to each model's raw service path; the service wall includes initial business answers, planning, successful and failed certification, waiting, scoring and logging. Model startup and common preflight precede this interval. Whiskers show the minimum and maximum of three paired process repetitions. (b) New prefill counts are per 600-business-request run; orange segments add certification, including witness tokens. Counts are initial scheduler prompt-minus-hit observations. (c) Coverage uses 1,620 future requests per model, giving 42.22%, 21.11% and 16.67%.

[PDF](fig2_strict_serving_performance.pdf) · [SVG](fig2_strict_serving_performance.svg) · [PNG](fig2_strict_serving_performance.png)

## Fig. 3. Certification Preserves Observed Free-Running Behavior

(a) Future routes in the faithful validation retain every raw/L0 request. Compiled requests are further divided by whether the paired raw reference receives a positive frozen task score. Qwen, Mistral and Llama have 684/684, 258/342 and 90/270 positive-score compiled pairs. (b) The earlier bounded-input audit (50 sources; single-session and template-fanout protocols) observed 0/2,442 compiled future output-ID differences. The faithful held-out validation (six sources; template fanout) observed 0/1,296. These are finite, scoped empirical observations. Positive scorer credit alone does not establish answer correctness. Tenant and process repetitions remain correlated; full-route score changes are retained in the supporting tables.

[PDF](fig3_observed_generation_behavior.pdf) · [SVG](fig3_observed_generation_behavior.svg) · [PNG](fig3_observed_generation_behavior.png)

## Fig. 4. Certification, PSTP and Service-Template Amortization

(a) The five-process same-engine control reports 500-ms SLO goodput of 1.472 req/s for D1's frozen safe layout and 1.428 req/s for full D2, including registration; whiskers are repeat min-max. D2 makes four verifier calls per trace. (b) Two separate live Qwen configurations each reject 10/10 harmful, dependency-valid layouts and publish zero rejected tokens. (c) The deployment certificate-granularity ablation holds the safe layout fixed across session/template modes. Across three repetitions of 1,125 future requests, calls per trace fall from 125 to 5 and unhidden cost falls from 25.05 to 3.24 ms per future request. The two measures use independent axes. Panel populations and protocols remain separate.

[PDF](fig4_certification_and_template_value.pdf) · [SVG](fig4_certification_and_template_value.svg) · [PNG](fig4_certification_and_template_value.png)

## Fig. 5. Service Scale and Physical KV Reuse

(a) The original deployment-template protocol measures absolute 500-ms SLO goodput under frozen open-arrival loads (Qwen3-8B; 25 authorized tenants per template; three fresh processes per condition). The 4.81x annotation is the 80%-load point. (b) The distinct 80-identity density condition reduces peak allocator-used blocks from 530 to 149 (71.9%) in a 2,386-block pool; minimum free blocks rise from 1,856 to 2,237. Registered tenant identities describe the authorized workload population, rather than simultaneously executing GPU requests. Block counts measure allocator occupancy. These original deployment protocols are separate from the strict closed-loop faithful-input study.

[PDF](fig5_service_scale_and_physical_reuse.pdf) · [SVG](fig5_service_scale_and_physical_reuse.svg) · [PNG](fig5_service_scale_and_physical_reuse.png)

## Fig. 6. Operating Region

(a) The 40-identity deployment sweep measures mean TTFT change against its paired native baseline as authorized sharing increases. Every point is derived from the saved CSV, including -3.2% at zero sharing. (b) A separate frozen working-set sweep compares round-robin and Zipf arrivals over 5, 25 and 50 active templates, showing net mean TTFT reduction. The plotted metric is latency reduction, with prefix-hit ratios retained in the data table. Together the panels delimit the measured reuse-density and residency region; qualification remains distinct from physical KV residency. Frozen-gate results are provided in a supporting table.

[PDF](fig6_operating_region.pdf) · [SVG](fig6_operating_region.svg) · [PNG](fig6_operating_region.png)
