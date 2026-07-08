# Phase 6 Runtime Prototype Closeout

## Status

Phase 6 is complete as a Python-level vLLM-serving prototype.

Artifacts:

- `docs/phase6a_proxy_skeleton_report.md`
- `docs/phase6b_controller_overhead_report.md`
- `docs/phase6c_tool_slack_copy_proxy_report.md`
- `docs/phase6d_runtime_replay_report.md`
- `results/runtime/contractkv_decision_logs.jsonl`
- `results/runtime/controller_overhead_v0.csv`
- `results/runtime/tool_slack_copy_proxy_v0.csv`
- `results/runtime/runtime_replay_policy_eval_v0.csv`

## What Was Proven

ContractKV can attach to a real OpenAI-compatible vLLM request path through a Python proxy. Qwen3-4B and Qwen3-8B both returned normal OpenAI-style responses through the proxy, while ContractKV emitted per-request decision logs.

The controller overhead is small in this prototype: mean policy time is about 0.09 ms and the maximum replay overhead ratio is about 1.35% against the Phase 2 reference TTFT model.

The CUDA transfer proxy shows that host/GPU copy on the critical path is visible, while a tool-slack window can hide part of the cost. Larger KV-sized transfers still leave residual stall.

The runtime replay keeps the Phase 5 conclusion intact: `ContractKV-Joint` admits the replay traces under budget, while `ContractKV-Indep` violates the quality budget.

## Boundaries

Phase 6 does not modify vLLM internals, FlashAttention, RoPE, or real KV precision kernels. It is a Python-level prototype with placement/prefetch/offload proxy behavior.

## Next Step

The next phase should decide whether to build a vLLM Python integration hook or keep ContractKV as an external serving proxy while adding richer segment traces and real tool-call slack windows.
