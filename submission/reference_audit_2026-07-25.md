# IEEE Reference Preparation Assistant Audit

Source package:
`E:\Downloads\IEEE-Reference-Submission-2026-07-25-07-05-47.zip`

## Findings

| Reference | IEEE RPA message | Independent verification | Action |
|---|---|---|---|
| Prompt Cache | Unable to style | The official MLSys record identifies the paper in *Proceedings of Machine Learning and Systems*, vol. 6, 2024. | Keep the existing citation. This is a tool-format limitation, not a metadata error. |
| CacheGen | First page should be 38, not 138 | ACM/Crossref metadata gives pages 38--56 and DOI `10.1145/3651890.3672274`. | Correct pages from 138--156 to 38--56 and add the DOI. |
| Jain fairness index | Journal title unrecognized | The original work is Digital Equipment Corporation Technical Report DEC-TR-301, September 1984. The prior ACM SIGMETRICS citation was not the original publication. | Replace the journal entry with the original technical report. |
| QoS-aware service recommendation | Year/page mismatch | The final IEEE Transactions on Services Computing issue is vol. 13, no. 6, pp. 1045--1058, Nov. 2020. The DOI encodes its 2017 early-access date. | Keep the final issue citation and DOI. The RPA warning reflects early-access metadata. |

## Additional Completion

- Added the official PagedAttention DOI: `10.1145/3600006.3613165`.
- Added the official LongBench DOI: `10.18653/v1/2024.acl-long.172`.
- Kept the official NeurIPS DOI for SGLang: `10.52202/079017-2000`.

## Submission Decision

The report contains no evidence that requires changing the paper's claims or
related-work discussion. The only material bibliographic corrections are the
CacheGen page range and the original Jain fairness-index source.
