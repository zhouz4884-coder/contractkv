#!/usr/bin/env python3
"""KV-sized tensor transfer proxy for Phase 6C."""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Any


FIELDS = [
    "mode",
    "kv_size_mb",
    "copy_ms",
    "decode_like_compute_ms",
    "observed_latency_ms",
    "estimated_stall_ms",
    "slack_window_ms",
    "bandwidth_gbps",
    "interference_note",
    "error_type",
    "error_message",
]


def estimate_stall_ms(copy_ms: float, slack_ms: float, mode: str) -> float:
    if mode == "no_copy":
        return 0.0
    if mode == "copy_in_tool_slack_window":
        return max(0.0, copy_ms - slack_ms)
    return copy_ms


def _cpu_sleep_case(size_mb: int, mode: str, repeat: int, slack_ms: float) -> dict[str, Any]:
    decode_ms = max(1.0, size_mb / 128.0)
    copy_ms = 0.0 if mode == "no_copy" else max(1.0, size_mb / 64.0)
    started = time.perf_counter()
    for _ in range(repeat):
        time.sleep(decode_ms / 1000.0)
        if mode == "copy_on_critical_path":
            time.sleep(copy_ms / 1000.0)
        elif mode == "copy_in_tool_slack_window":
            time.sleep(estimate_stall_ms(copy_ms, slack_ms, mode) / 1000.0)
    observed = (time.perf_counter() - started) * 1000 / max(repeat, 1)
    return {
        "mode": mode,
        "kv_size_mb": size_mb,
        "copy_ms": round(copy_ms, 6),
        "decode_like_compute_ms": round(decode_ms, 6),
        "observed_latency_ms": round(observed, 6),
        "estimated_stall_ms": round(estimate_stall_ms(copy_ms, slack_ms, mode), 6),
        "slack_window_ms": slack_ms,
        "bandwidth_gbps": round((size_mb / 1024) / (copy_ms / 1000), 6) if copy_ms > 0 else 0.0,
        "interference_note": "cpu_fallback_proxy",
        "error_type": "none",
        "error_message": "",
    }


def _torch_case(size_mb: int, mode: str, repeat: int, slack_ms: float) -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        return _cpu_sleep_case(size_mb, mode, repeat, slack_ms)
    device = torch.device("cuda:0")
    numel = size_mb * 1024 * 1024 // 2
    host = torch.empty(numel, dtype=torch.float16, pin_memory=True)
    gpu = torch.empty(numel, dtype=torch.float16, device=device)
    stream = torch.cuda.Stream()
    decode_iters = max(4, size_mb // 64)
    mat = torch.randn((512, 512), device=device, dtype=torch.float16)

    def decode_like():
        out = mat
        for _ in range(decode_iters):
            out = out @ mat
        return out

    torch.cuda.synchronize()
    decode_like()
    if mode != "no_copy":
        gpu.copy_(host, non_blocking=False)
    torch.cuda.synchronize()
    started = torch.cuda.Event(enable_timing=True)
    ended = torch.cuda.Event(enable_timing=True)
    copy_started = torch.cuda.Event(enable_timing=True)
    copy_ended = torch.cuda.Event(enable_timing=True)
    copy_ms_values = []
    total_ms_values = []
    for _ in range(repeat):
        torch.cuda.synchronize()
        started.record()
        if mode == "copy_in_tool_slack_window":
            with torch.cuda.stream(stream):
                copy_started.record(stream)
                gpu.copy_(host, non_blocking=True)
                copy_ended.record(stream)
            decode_like()
            stream.synchronize()
        elif mode == "copy_on_critical_path":
            copy_started.record()
            gpu.copy_(host, non_blocking=False)
            copy_ended.record()
            decode_like()
        else:
            copy_started.record()
            copy_ended.record()
            decode_like()
        ended.record()
        torch.cuda.synchronize()
        copy_ms_values.append(copy_started.elapsed_time(copy_ended))
        total_ms_values.append(started.elapsed_time(ended))
    copy_ms = sum(copy_ms_values) / len(copy_ms_values)
    observed = sum(total_ms_values) / len(total_ms_values)
    decode_ms = max(0.0, observed - (copy_ms if mode == "copy_on_critical_path" else 0.0))
    return {
        "mode": mode,
        "kv_size_mb": size_mb,
        "copy_ms": round(copy_ms, 6),
        "decode_like_compute_ms": round(decode_ms, 6),
        "observed_latency_ms": round(observed, 6),
        "estimated_stall_ms": round(estimate_stall_ms(copy_ms, slack_ms, mode), 6),
        "slack_window_ms": slack_ms,
        "bandwidth_gbps": round((size_mb / 1024) / (copy_ms / 1000), 6) if copy_ms > 0 else 0.0,
        "interference_note": "cuda_pinned_stream_proxy",
        "error_type": "none",
        "error_message": "",
    }


def run_proxy_case(size_mb: int, mode: str, repeat: int = 3, slack_ms: float = 10.0, device: str = "auto") -> dict[str, Any]:
    try:
        if device == "cpu":
            return _cpu_sleep_case(size_mb, mode, repeat, slack_ms)
        return _torch_case(size_mb, mode, repeat, slack_ms)
    except Exception as exc:  # pragma: no cover - hardware-dependent fallback
        row = _cpu_sleep_case(size_mb, mode, repeat, slack_ms)
        row["error_type"] = "proxy_fallback"
        row["error_message"] = str(exc)
        return row


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes-mb", default="128,256,512,1024")
    parser.add_argument("--modes", default="no_copy,copy_on_critical_path,copy_in_tool_slack_window")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--slack-ms", type=float, default=10.0)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu"])
    parser.add_argument("--output", type=Path, default=Path("results/runtime/tool_slack_copy_proxy_v0.csv"))
    args = parser.parse_args()
    rows = []
    for size in [int(item) for item in args.sizes_mb.split(",") if item]:
        for mode in [item for item in args.modes.split(",") if item]:
            rows.append(run_proxy_case(size, mode, args.repeat, args.slack_ms, args.device))
    write_csv(args.output, rows)
    print(f"rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
