#!/usr/bin/env python3
"""Measure host/device transfer bandwidth and copy/decode interference."""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bench_openai_ttft_tpot import current_commit


TRANSFER_FIELDS = [
    "timestamp",
    "direction",
    "src",
    "dst",
    "block_mb",
    "pinned",
    "warmup_iters",
    "iters",
    "median_ms",
    "mean_ms",
    "bandwidth_gbps",
    "error_type",
    "error_message",
    "commit_hash",
]

INTERFERENCE_FIELDS = [
    "timestamp",
    "mode",
    "copy_bandwidth_GBps",
    "decode_tpot_ms_without_copy",
    "decode_tpot_ms_with_copy",
    "slowdown_percent",
    "error_type",
    "error_message",
    "commit_hash",
]


def parse_block_sizes(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def bandwidth_gbps(block_mb: int, milliseconds: float) -> float:
    if milliseconds <= 0:
        return 0.0
    bytes_moved = block_mb * 1024 * 1024
    return round((bytes_moved / (milliseconds / 1000.0)) / 1_000_000_000, 3)


def slowdown_percent(without_copy_ms: float, with_copy_ms: float) -> float | str:
    if without_copy_ms <= 0:
        return ""
    return round(((with_copy_ms - without_copy_ms) / without_copy_ms) * 100.0, 3)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _timed_cuda_copy(torch: Any, src: Any, dst: Any, iters: int, warmup: int) -> list[float]:
    times = []
    for i in range(warmup + iters):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        torch.cuda.synchronize()
        start.record()
        dst.copy_(src, non_blocking=True)
        end.record()
        torch.cuda.synchronize()
        if i >= warmup:
            times.append(start.elapsed_time(end))
    return times


def _transfer_rows(torch: Any, block_sizes: list[int], warmup: int, iters: int, commit: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    h2d_rows, d2h_rows, p2p_rows = [], [], []
    for block_mb in block_sizes:
        elements = block_mb * 1024 * 1024 // 4
        for pinned in (False, True):
            host = torch.empty(elements, dtype=torch.float32, pin_memory=pinned)
            dev = torch.empty(elements, dtype=torch.float32, device="cuda:0")
            for direction, rows, src, dst in (
                ("h2d", h2d_rows, host, dev),
                ("d2h", d2h_rows, dev, host),
            ):
                try:
                    times = _timed_cuda_copy(torch, src, dst, iters, warmup)
                    rows.append(_transfer_row(direction, "host" if direction == "h2d" else "gpu0", "gpu0" if direction == "h2d" else "host", block_mb, pinned, warmup, iters, times, "none", "", commit))
                except Exception as exc:
                    rows.append(_transfer_row(direction, "", "", block_mb, pinned, warmup, iters, [], "copy_error", str(exc), commit))

        if torch.cuda.device_count() >= 2:
            try:
                src = torch.empty(elements, dtype=torch.float32, device="cuda:0")
                dst = torch.empty(elements, dtype=torch.float32, device="cuda:1")
                times = _timed_cuda_copy(torch, src, dst, iters, warmup)
                p2p_rows.append(_transfer_row("p2p", "gpu0", "gpu1", block_mb, "", warmup, iters, times, "none", "", commit))
            except Exception as exc:
                p2p_rows.append(_transfer_row("p2p", "gpu0", "gpu1", block_mb, "", warmup, iters, [], "p2p_unavailable", str(exc), commit))
        else:
            p2p_rows.append(_transfer_row("p2p", "gpu0", "gpu1", block_mb, "", warmup, iters, [], "p2p_unavailable", "fewer than two CUDA devices", commit))
    return h2d_rows, d2h_rows, p2p_rows


def _transfer_row(direction: str, src: str, dst: str, block_mb: int, pinned: Any, warmup: int, iters: int, times: list[float], error_type: str, error_message: str, commit: str) -> dict[str, Any]:
    median = round(statistics.median(times), 3) if times else ""
    mean = round(statistics.mean(times), 3) if times else ""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "src": src,
        "dst": dst,
        "block_mb": block_mb,
        "pinned": pinned,
        "warmup_iters": warmup,
        "iters": iters,
        "median_ms": median,
        "mean_ms": mean,
        "bandwidth_gbps": bandwidth_gbps(block_mb, median) if median != "" else "",
        "error_type": error_type,
        "error_message": error_message,
        "commit_hash": commit,
    }


def _decode_proxy_ms(torch: Any, iters: int, copy: str | None = None, block_mb: int = 64, warmup: int = 5) -> float:
    a = torch.randn((2048, 2048), device="cuda:0", dtype=torch.float16)
    b = torch.randn((2048, 2048), device="cuda:0", dtype=torch.float16)
    elements = block_mb * 1024 * 1024 // 4
    host = torch.empty(elements, dtype=torch.float32, pin_memory=True)
    dev = torch.empty(elements, dtype=torch.float32, device="cuda:0")
    for _ in range(warmup):
        _ = a @ b
        if copy == "h2d":
            dev.copy_(host, non_blocking=True)
        elif copy == "d2h":
            host.copy_(dev, non_blocking=True)
    torch.cuda.synchronize()
    started = time.perf_counter()
    for _ in range(iters):
        _ = a @ b
        if copy == "h2d":
            dev.copy_(host, non_blocking=True)
        elif copy == "d2h":
            host.copy_(dev, non_blocking=True)
    torch.cuda.synchronize()
    return ((time.perf_counter() - started) * 1000.0) / iters


def _interference_rows(torch: Any, commit: str) -> list[dict[str, Any]]:
    rows = []
    try:
        base = _decode_proxy_ms(torch, 20)
        h2d = _decode_proxy_ms(torch, 20, copy="h2d")
        d2h = _decode_proxy_ms(torch, 20, copy="d2h")
        for mode, with_copy in (("decode_only", base), ("decode_plus_h2d_copy", h2d), ("decode_plus_d2h_copy", d2h)):
            rows.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "mode": mode,
                    "copy_bandwidth_GBps": "",
                    "decode_tpot_ms_without_copy": round(base, 3),
                    "decode_tpot_ms_with_copy": round(with_copy, 3),
                    "slowdown_percent": slowdown_percent(base, with_copy),
                    "error_type": "none",
                    "error_message": "",
                    "commit_hash": commit,
                }
            )
        rows.insert(
            0,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "copy_only",
                "copy_bandwidth_GBps": "",
                "decode_tpot_ms_without_copy": "",
                "decode_tpot_ms_with_copy": "",
                "slowdown_percent": "",
                "error_type": "none",
                "error_message": "",
                "commit_hash": commit,
            },
        )
    except Exception as exc:
        rows.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "decode_proxy",
                "copy_bandwidth_GBps": "",
                "decode_tpot_ms_without_copy": "",
                "decode_tpot_ms_with_copy": "",
                "slowdown_percent": "",
                "error_type": "interference_error",
                "error_message": str(exc),
                "commit_hash": commit,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="results/hardware")
    parser.add_argument("--block-mb", default="1,4,16,64,256,512")
    parser.add_argument("--warmup-iters", type=int, default=5)
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--commit-hash", default=None)
    args = parser.parse_args()
    commit = args.commit_hash or current_commit()
    output_dir = Path(args.output_dir)

    try:
        import torch
    except Exception as exc:
        rows = [_transfer_row("h2d", "host", "gpu0", 0, "", args.warmup_iters, args.iters, [], "torch_import_error", str(exc), commit)]
        _write_csv(output_dir / "h2d_bandwidth.csv", TRANSFER_FIELDS, rows)
        _write_csv(output_dir / "d2h_bandwidth.csv", TRANSFER_FIELDS, rows)
        _write_csv(output_dir / "p2p_bandwidth.csv", TRANSFER_FIELDS, rows)
        _write_csv(output_dir / "copy_decode_interference.csv", INTERFERENCE_FIELDS, [])
        return 1

    if not torch.cuda.is_available():
        rows = [_transfer_row("h2d", "host", "gpu0", 0, "", args.warmup_iters, args.iters, [], "cuda_unavailable", "torch.cuda.is_available() is false", commit)]
        _write_csv(output_dir / "h2d_bandwidth.csv", TRANSFER_FIELDS, rows)
        _write_csv(output_dir / "d2h_bandwidth.csv", TRANSFER_FIELDS, rows)
        _write_csv(output_dir / "p2p_bandwidth.csv", TRANSFER_FIELDS, rows)
        _write_csv(output_dir / "copy_decode_interference.csv", INTERFERENCE_FIELDS, [])
        return 1

    h2d, d2h, p2p = _transfer_rows(torch, parse_block_sizes(args.block_mb), args.warmup_iters, args.iters, commit)
    _write_csv(output_dir / "h2d_bandwidth.csv", TRANSFER_FIELDS, h2d)
    _write_csv(output_dir / "d2h_bandwidth.csv", TRANSFER_FIELDS, d2h)
    _write_csv(output_dir / "p2p_bandwidth.csv", TRANSFER_FIELDS, p2p)
    _write_csv(output_dir / "copy_decode_interference.csv", INTERFERENCE_FIELDS, _interference_rows(torch, commit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
