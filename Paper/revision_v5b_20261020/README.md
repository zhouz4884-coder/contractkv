# ContractKV V5b — manuscript and evidence integration

The main manuscript is `contractkv_tsc_v5b.pdf` (12 pages). Its editable source is `contractkv_tsc_v5b.tex` and `sections/`. The final half-column on page 12 reserves one quarter of a two-column page for author-confirmed biographies. No biography details were invented.

The supplement is `contractkv_supplement.pdf` (11 pages). Figures 1–2 span two columns; Figures 3–6 are single-column vector figures. `figures/Fig1-6_review.pdf` collects the current six figures.

This revision strengthens the shared-service-object argument, promotes the completed all-route physical authorization experiment, updates Fig.4 to the actual 180-candidate rejection matrix, and delivers the statistical/structural/arrival records in the supplement. All experimental inputs, results and admission thresholds are unchanged. The experimental fusion/residency study remains an appendix. No GPU experiments or Response Letter were produced in this manuscript round.

## Rebuild

Requirements: Python with matplotlib, numpy, PyMuPDF and Pillow; MiKTeX/TeX Live with `pdflatex` and the packages in the manuscript preamble. The included six vector figures can be used directly.

```powershell
python -B scripts/plot_fig4_v5b.py
python -B scripts/build.py
python -B scripts/qa_v5b.py
python -B scripts/reproduce_v5b.py --output PATH_TO_A_NEW_DIRECTORY
```

`build.py` compiles each manuscript three times with shell escape disabled. The independent rebuild compares all page text and half-scale pixels, plus regenerated Fig.4 PDF/SVG/PNG bytes. It makes no model calls. Its receipt is `audit/independent_reproduction_v5b.json`; defined content/layout/source checks are in `audit/manuscript_QA_v5b.json`.

`evidence/V5b_evidence_register_v1.json` identifies newly incorporated, unmodified source summaries and their hashes. The legacy restore scripts are retained for the inherited data workflow; the V5b build uses the already frozen evidence files and the commands above.

The experiment versions remain separate: primary query-qualified complete-wall results, deployment-template amortization/open-arrival controls, complete-cost replay, authorization regression and exploratory exact-scope work. A later patch is never assigned retroactively to an earlier performance measurement.

See `V5b_revision_record_zh.md` for the completed revision record. Final reviewer-response page/line mapping should use this rebuilt manuscript and will be prepared separately.
