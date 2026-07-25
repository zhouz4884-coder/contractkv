# ContractKV IEEE TSC Submission Closure

## Manuscript

- [x] Main manuscript compiles in two clean `pdflatex` passes.
- [x] Main manuscript remains exactly 12 pages.
- [x] References use 7.5-pt type; an 8-pt trial exceeded the 12-page limit.
- [x] Abstract and main figures are unchanged.
- [x] Introduction contains one current-runtime relevance sentence.
- [x] Implementation reports the vLLM 0.25.1 protocol and measured effect.
- [x] Limitations distinguish backend adaptation from abstraction validity.
- [x] No undefined references, undefined citations, or overfull boxes remain.
- [x] All 12 rendered pages were inspected for clipping and overlap.

## Supplementary Material

- [x] The vLLM 0.25.1 audit is packaged as a one-page supplement.
- [x] Runtime identity, fresh-process protocol, and source integrity are stated.
- [x] Task pass and paired-output equality are reported separately.
- [x] RULER mean TTFT/new-prefill reductions are 79.84%/94.20%.
- [x] HotpotQA mean TTFT/new-prefill reductions are 96.77%/99.53%.
- [x] Paired output equality is 100% with zero task-score delta.
- [x] Hook availability and the non-drop-in PSTP boundary are explicit.

## Clean Package

- [x] Package contains only the manuscript, supplement, referenced figures,
      build instructions, and integrity hashes.
- [x] Figure generators, scene metadata, internal checklists, logs, auxiliary
      files, QA renders, and experiment work files are excluded.
- [x] Text and binary scans find no ChatGPT, Codex, Claude, Gemini,
      `created_by`, `.codex`, or `.qoder` markers.
- [x] PDF metadata contains only LaTeX/pdfTeX or Matplotlib producers.
- [x] The extracted package compiles independently to 12 manuscript pages and
      one supplementary page.
- [x] All 11 payload files match `SHA256SUMS.txt`.

## Deliverable

- Archive: `submission/contractkv_tsc_submission_2026-07-25.zip`
- SHA-256:
  `e9f069b5075dc2329fb241d81026ca846cbac86d0ae89cca675a5d9aa4dbc607`
- Claim boundary: the vLLM 0.25.1 experiment establishes current-runtime
  structural relevance and adaptation feasibility, not a complete port of
  online certification or PSTP.
