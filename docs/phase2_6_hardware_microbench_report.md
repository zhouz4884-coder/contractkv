# Phase 2.6 Hardware Microbenchmark Report

This report is generated from the hardware CSV files in `results/hardware/`.

The purpose is to estimate how much KV movement can be hidden under tool-call slack windows and whether copy traffic interferes with decode-like GPU work.

## Result

Phase 2.6 completed with `error_type=none` for H2D, D2H, P2P, and copy/decode interference rows.

Best observed bandwidth:

| Direction | Best block MB | Pinned | Bandwidth GB/s |
| --- | ---: | --- | ---: |
| Host to GPU | 512 | true | 13.207 |
| GPU to Host | 512 | true | 13.199 |
| GPU0 to GPU1 | 4 | n/a | 5.825 |

Copy/decode interference proxy:

| Mode | Decode proxy ms | Slowdown |
| --- | ---: | ---: |
| decode only | 0.282 | 0.0% |
| decode plus H2D copy | 5.372 | 1803.666% |
| decode plus D2H copy | 5.373 | 1803.964% |

This is a torch matmul proxy, not full vLLM decode. It supports the scheduling motivation that copy traffic should be placed in slack windows rather than assumed free.
