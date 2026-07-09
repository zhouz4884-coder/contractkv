# Phase 11B SSPP Tool-Slack Pipeline Report

## Goal

Evaluate SSPP: Speculative Segment Preparation Pipeline.

SSPP moves segment preparation out of the next LLM turn's TTFT critical path and into agent tool slack:

```text
pre-hash
pre-tokenize
pre-fetch
pre-quantize stub
```

## Setup

Inputs:

```text
results/runtime/tool_slack_copy_proxy_v0.csv
```

Slack buckets:

```text
0 ms
50 ms
100 ms
200 ms
500 ms
```

Prediction hit rates:

```text
1.0
0.75
0.5
```

Output:

```text
results/segment_fabric/sspp_tool_slack_pipeline_v0.csv
```

## Results

Overall:

```text
rows = 105
prepare_actions = 7
mean_hidden_fraction at prediction_hit_rate=1.0 = 0.789
```

At prediction hit rate 1.0:

| Tool Slack ms | Mean Hidden Fraction | Mean Critical Path ms |
| ---: | ---: | ---: |
| 0 | 0.000 | 24.223 |
| 50 | 0.945 | 4.477 |
| 100 | 1.000 | 0.000 |
| 200 | 1.000 | 0.000 |
| 500 | 1.000 | 0.000 |

At 50 ms slack:

| Prepare Action | Work ms | Hidden Fraction | Critical Path ms |
| --- | ---: | ---: | ---: |
| prehash_segments | 1.000 | 1.000 | 0.000 |
| pretokenize_1k_tokens | 4.000 | 1.000 | 0.000 |
| prequant_int4_1k_tokens_stub | 12.000 | 1.000 | 0.000 |
| prefetch_128mb | 10.199 | 1.000 | 0.000 |
| prefetch_256mb | 20.354 | 1.000 | 0.000 |
| prefetch_512mb | 40.666 | 1.000 | 0.000 |
| prefetch_1024mb | 81.340 | 0.615 | 31.340 |

## Interpretation

SSPP gives ContractKV a regime where it can help even without capacity failure:

```text
tool-call gap exists
next-turn segment state is predictable
preparation work is smaller than slack
```

The 50 ms slack bucket hides all small/medium preparation actions and most of a 1 GB prefetch. At 100 ms, all tested actions are fully hidden.

## Claim Boundary

Supported:

```text
Tool slack can hide segment preparation work under the measured/proxy action costs.
Prediction misses are explicitly charged as wasted work.
```

Not claimed:

```text
real vLLM KV precompute
real KIVI pre-quantization
production scheduler overlap correctness
```

The next hard-system step is to attach SSPP decisions to real vLLM request metadata and measure TTFT after tool return.
