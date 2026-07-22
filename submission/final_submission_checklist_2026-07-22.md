# ContractKV Final Submission Checklist

## Final review closure

- [x] Fig. 1 retained without structural redraw.
- [x] Fig. 1 labels use `CALC: contract-aware layout compiler` and
      `In-engine teacher-forced verifier`.
- [x] Problem 1 selects the highest passing member of the frozen ladder and
      exactly matches high-to-low runtime descent.
- [x] The expanded dependency-graph complexity is stated as
      `O(|E'| + |V'| log |V'|)`.
- [x] Service manifest `M` and model configuration `Gamma` no longer collide.
- [x] Means and request quantiles use complete-cell pooled requests; clustered
      inference preserves fresh-process and paired-session units.
- [x] Global and common-scope tables distinguish policy-attributable
      regressions from raw-fallback events.
- [x] The Llama raw-versus-raw control rate is reported as 0.044%.
- [x] Certificate authentication is described as HMAC-SHA256, matching the
      implementation rather than claiming a public-key signature.
- [x] Scope-granularity claims report exact TTFT, p99, and prefix-hit values.
- [x] The conclusion reports an approximately 112x lower observed
      material-regression rate.
- [x] Figs. 2--6 use the multiplication sign in rendered annotations.

## Preserved headline evidence

- Four configurations remain net-positive across all workflows: 29.41--44.69%
  net mean-TTFT reduction with fallback and residual verification charged.
- Same-engine Qwen3-8B D2 reduces mean TTFT by 92.90% with registration wall
  time charged.
- The 25-tenant load sweep improves 500-ms SLO goodput by 4.81x.
- The 80-tenant physical-dedup cell reduces peak KV-block occupancy by 72%.
- The Llama matched-runtime comparison reports 29.16% reduction for ContractKV
  versus 26.96% for CacheBlend, with 0/1,125 admitted compiled regressions.
- Live fault probes and 325,000 deterministic state-machine transactions show
  no partial publication or stale-scope admission.

## Build and visual QA

- [x] `pdflatex` completes twice with no undefined references.
- [x] Final PDF is exactly 12 pages.
- [x] No overfull boxes remain in the final LaTeX log.
- [x] All 12 pages were rendered and inspected.
- [x] Formulae, Tables II--IV, Figs. 1--6, and the final reference column are
      legible and unclipped.
- [x] The clean package compiles independently using only its included files.
