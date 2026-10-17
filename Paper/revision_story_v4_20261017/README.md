# ContractKV Story V4 — manuscript and layout revision

This directory preserves a self-contained revision of Story V3. It contains the
12-page main manuscript, a 8-page supplement, six editable vector figures, frozen
source records, aggregation scripts and actual-output QA.

The main paper reserves exactly one quarter of a two-column text page for the
two authors' biographies. That region is deliberately blank. Replace
`sections/author_biographies.tex` with author-confirmed biography entries before
submission, then rebuild and check pagination. No personal histories or portraits
have been invented. This is a manuscript-review package, not a complete final
submission bundle; the Response Letter is deferred.

## Main changes

- Figure 1 separates the authenticated deployment certificate, controlled-client
  query admission records, and physical prefix identity. Its commit boundary
  explicitly contains certified stable full blocks.
- The deployment breadth table contains only that cohort's residual-slack TTFT,
  prefill and slack values. Independent zero-slack registration-cost accounting
  appears in a separately numbered supplemental table.
- A method comparison table specifies the two qualification protocols. The
  trust-model subsection describes semantic operator misconfiguration, the
  registration helper's CPU-only evidence, and the timing-channel boundary.
- Supplemental tables give every primary source/model's quality, coverage and
  p99, all nine manifest cases, and the archived open-arrival interval.
- Figure 5 restores the absolute goodput-increase interval. Its point estimates
  were cross-checked against the frozen aggregate; the bootstrap was not rerun.

The V4a evidence audit adds separately labelled five-family structural controls,
a same-four-source input comparison, matched-request historical RPC accounting,
and CPU checks of the actual client binding function. All four original reported
deployment means are reproduced. Complete historical controller cost is not
recoverable: 33 Llama intermediate/failed RPC timers and other exception-path
timers are missing. The original 85.0%/2.4% motivation aggregates remain
unverified; these new tables do not claim to reproduce them. HMAC checking occurs
in the trusted deployment client, with application authorization required for
the domain wildcard. No independent public authentication proxy is asserted.

Primary measurements and acceptance rules are unchanged. There are no new GPU
experiments or new selected sources. Figures 1–2 remain double-column; 3–6 remain
single-column. The hollow repetition dots removed at the author's request have
not been reintroduced.

## Rebuild

Use the pinned dependencies in `requirements.txt`, an IEEEtran-capable TeX
installation, and the recorded fonts. The build script invokes the inspected
no-shell-escape compiler wrapper and performs three passes for each document.

```powershell
python -B scripts/restore_evidence.py
python -B scripts/restore_revision_audit.py
python -B scripts/restore_closure_tables.py
python -B scripts/plot_figures.py
python -B scripts/plot_architecture.py
python -B scripts/build.py
python -B scripts/qa.py
python -B scripts/locate_evidence.py
python -B scripts/reproduce.py --output ../../.artifacts/story_v4a_rebuild
python -B scripts/package.py ../../submission/ContractKV_story_v4a_20261017.zip
```

`audit/manuscript_QA.json` checks actual PDFs, embedded fonts, vector exports,
numerical identities and the measured biography reservation. The reservation
uses 348 TeX points in a column of a 696-point text area: 25% of a two-column
page. `audit/evidence_locations.csv` gives compiled section/table/figure numbers,
PDF pages and TeX source lines; it is not printed PDF line numbering or a
Response Letter.

`evidence/revision_audit_evidence.json` retains all 18 source/model rows and the
input-file hashes. Source-level p99 and quality are recomputed; the archived
goodput interval is identified as restored, not newly estimated. The CPU manifest
helper's acceptance of a trusted semantic mislabel remains a negative result.

`audit/evidence_provenance_audit_zh.md` records the source-search findings and
unresolved historical data, independently of the manuscript narrative. The
Response Letter is still deferred. QA verifies these boundaries as stated; a
QA PASS does not mean that missing historical measurements have been recovered.
