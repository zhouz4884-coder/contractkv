# Phase 16A Preemptible Micro-Chunk Scheduler

## Goal

Phase 15D showed that treating shadow canary work as ordinary endpoint traffic
can raise active p95 TTFT by about 585 ms. Phase 16A tests the scheduling idea
from the design note: shadow verification should run only in idle, bounded
micro-chunks. The claim is not zero interference; it is one-micro-chunk bounded
interference.

## Method

This is an executable scheduler model, not a vLLM source patch. The model uses
the same active foreground arrival stream for all policies and compares:

- baseline
- naive ordinary shadow
- IDLE_ONLY micro-chunks of 16, 32, 64, and 128 tokens

Each policy runs five seeds, two slack budgets, and 400 foreground active
requests per slack point. Shadow verification work is 4K tokens.

## Result

At 2 s slack:

| Policy | Active p95 penalty | Active p99 penalty | Shadow completion |
| --- | ---: | ---: | ---: |
| naive ordinary shadow | 444.8 ms | 490.8 ms | 100% |
| IDLE_ONLY-16 | 2.7 ms | 4.1 ms | 100% |
| IDLE_ONLY-32 | 4.2 ms | 5.9 ms | 100% |
| IDLE_ONLY-64 | 8.2 ms | 8.9 ms | 100% |
| IDLE_ONLY-128 | 14.0 ms | 17.7 ms | 100% |

At 500 ms slack, IDLE_ONLY-16/32/64 keep foreground penalty bounded and safely
starve/cancel shadow work; IDLE_ONLY-128 exceeds the p95 penalty target.

## Interpretation

The result supports the scheduler design rule: chunk size is a control knob.
16/32/64-token chunks satisfy the foreground interference gate in this model,
while 128-token chunks are too large. The correct next step is a vLLM source-
level scheduler hook, not a claim that the model already proves production
behavior.

## Artifacts

- `scripts/phase16a_microchunk_scheduler.py`
- `results/runtime/phase16a_microchunk_scheduler_raw_v0.csv`
- `results/runtime/phase16a_microchunk_scheduler_summary_v0.csv`
