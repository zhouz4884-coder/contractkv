# Phase 13B Live vLLM Replay Harness

## Purpose

Phase 13B takes the Phase 13A control-plane ledger and prepares it for live OpenAI-compatible vLLM serving.

The main comparison remains:

```text
vLLM raw-order
ContractKV-CAPOSC
ContractKV-CAPOSC + SSPP
ContractKV-CAPOSC + SSPP + RAR
```

Phase 13B is split into two tiers:

```text
B-1 live-serving replay:
  concurrency = 1 / 2 / 4
  SLO = 300 / 500 / 700 ms
  goal = validate live TTFT / TPOT / latency / SLO req/s for CAPOSC and SSPP.

B-2 live-pressure replay:
  concurrency = 6 / 8 / 10
  SLO = 300 / 500 / 700 ms
  goal = validate capacity failures, timeouts, RAR events, block-free accounting, and completion rate.
```

## SSPP Boundary

The harness makes SSPP mode explicit:

```text
real_lightweight:
  performs real Python-side prompt/layout/hash preparation before request submission,
  records prepare_ms and whether tool_slack_ms could hide it,
  does not subtract time from measured vLLM TTFT.

accounting:
  records the Phase 13A-style estimated preparation work,
  useful for sensitivity analysis,
  must not be described as live overlap.
```

This prevents SSPP from being accidentally written as a time-subtraction trick.

## RAR Boundary

The harness records planned RAR fields:

```text
rar_trigger_reason
rar_events
blocks_freed
free_block_delta
recompute_tokens_saved
```

For hard-system claims, these must be backed by vLLM actuator logs:

```text
RAR_trigger_reason = block_pressure
suffix_blocks_freed
free_block_delta > 0
request_completed = true
```

If live high-pressure replay does not trigger RAR, the result should be reported as a pressure-calibration failure, not fabricated into a success.

## Dry-Run Verification

Local mock dry-run command:

```powershell
python scripts\phase13b_live_replay.py `
  --mock `
  --trajectories-per-type 1 `
  --turns 2 `
  --concurrencies 1,2,4,6 `
  --slo-buckets-ms 300,500,700 `
  --sspp-mode real_lightweight
```

Dry-run artifacts:

```text
results/end_to_end/phase13b_live_replay_mock_raw_v0.csv
results/end_to_end/phase13b_live_replay_mock_summary_v0.csv
```

These files only prove the live harness schema and control flow. They are not fresh live vLLM goodput.

## Live B-1 Command

Run this after Qwen3-8B vLLM is available at `http://localhost:8001/v1`:

```bash
conda activate contractkv-cu128
cd /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv

python scripts/phase13b_live_replay.py \
  --base-url http://localhost:8001/v1 \
  --model qwen3-8b \
  --trajectories-per-type 1 \
  --turns 2 \
  --concurrencies 1,2,4 \
  --slo-buckets-ms 300,500,700 \
  --sspp-mode real_lightweight \
  --raw-output results/end_to_end/phase13b_live_b1_raw_v0.csv \
  --summary-output results/end_to_end/phase13b_live_b1_summary_v0.csv
```

Expected interpretation:

```text
CAPOSC should improve or preserve TTFT versus raw-order.
SSPP real_lightweight should report prepare_ms and hidden_fraction.
SSPP should not be claimed as TTFT subtraction.
```

## Live B-2 Command

Only run B-2 after B-1 is clean:

```bash
python scripts/phase13b_live_replay.py \
  --base-url http://localhost:8001/v1 \
  --model qwen3-8b \
  --trajectories-per-type 1 \
  --turns 2 \
  --concurrencies 6,8,10 \
  --slo-buckets-ms 300,500,700 \
  --sspp-mode real_lightweight \
  --raw-output results/end_to_end/phase13b_live_b2_pressure_raw_v0.csv \
  --summary-output results/end_to_end/phase13b_live_b2_pressure_summary_v0.csv
```

Required companion logs:

```text
vLLM server log
RAR actuator/probe log, if enabled
nvidia-smi sampling log
HTTP error/timeout records
```

## Quality Sanity

Each request records:

```text
quality_sanity
quality_score
output_text
error_type
error_message
```

This is marker/order sanity, not official benchmark scoring. Phase 13B should be followed by a small real-task scoring pass:

```text
RULER niah
LongBench hotpotqa / qasper / narrativeqa
RepoBench python completion
mixed-agent marker + order + task answer
```

Success criterion:

```text
quality drop <= 0.03
violated_edges = 0
RepoBench does not repeat the Phase 12C canonical-all failure mode.
```

## Artifacts

```text
scripts/phase13b_live_replay.py
tests/test_phase13b_live_replay.py
results/end_to_end/phase13b_live_replay_mock_raw_v0.csv
results/end_to_end/phase13b_live_replay_mock_summary_v0.csv
```

## Claim Boundary

The current Phase 13B artifacts are a live-ready harness plus mock dry-run outputs.

They do not yet claim:

```text
fresh live vLLM goodput,
real vLLM capacity failure reduction,
real RAR hard-system improvement,
official benchmark quality preservation.
```

Those claims require the B-1/B-2 live commands above and the companion vLLM/RAR logs.
