# Phase 23 Closeout: Model Onboarding and Scale-Up

Phase 23 closes two reviewer-facing questions.

First, new-model qualification is affordable. The conservative Llama layout ladder used 25 sessions, 0.3586 GPU-hours, a 1,678-byte manifest, and a 0.2 microsecond p95 runtime lookup. Exact subset analysis shows five samples per family are sufficient for stable selection across all five families.

Second, ContractKV scales beyond the 8B mainline. Qwen3-14B on two RTX 3090 GPUs achieves a 44.69% net mean TTFT reduction, a 30.12% p95 reduction, and a 60.57% new-prefill reduction across three fresh process pairs, with 99.9725% certified prefix physical reuse and zero policy quality violations.

The layout-ladder ablation also narrows the claim. Certificate-guided descent is not a universal completion booster: completion is already 100% in this workload. Its defensible role is to remove unsafe high-level admissions and recover safe lower-level coverage when such a certificate exists. On sealed held-out data it raises safe completed coverage from 48% to 50% while preserving quality.

The resulting paper story is stronger because the control-plane cost, safety tradeoff, and larger-model serving benefit are all measured separately rather than inferred from one headline latency number.
