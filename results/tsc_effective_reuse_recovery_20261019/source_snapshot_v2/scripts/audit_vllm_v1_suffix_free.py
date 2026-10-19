#!/usr/bin/env python3
"""Audit whether vLLM V1 can safely probe suffix-only KV release."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path


FOCUS_FILES = [
    "v1/core/kv_cache_manager.py",
    "v1/core/block_pool.py",
    "v1/core/sched/scheduler.py",
]

RUNTIME_INVARIANTS = [
    "prefix_blocks_retained_exact",
    "suffix_blocks_freed_exact",
    "free_gpu_blocks_delta_gte_suffix_blocks_freed",
    "num_computed_tokens_after_equals_anchor_token_end",
    "request_completed",
    "response_non_empty",
    "duplicate_block_id_not_detected",
    "block_table_consistency",
]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return ""


def audit_suffix_free_path(vllm_root: Path) -> dict:
    files = {}
    for rel in FOCUS_FILES:
        text = _read(vllm_root / rel)
        files[rel] = {
            "exists": bool(text),
            "has_get_block_ids": "get_block_ids" in text,
            "has_request_free": "def free(" in text and "request" in text,
            "has_coordinator_free": "coordinator.free" in text,
            "has_block_pool_free": "free_block" in text or "free_blocks" in text or "free(" in text,
            "has_num_computed_tokens": "num_computed_tokens" in text,
            "has_block_table": "block_table" in text or "get_block_ids" in text,
        }
    kv = files["v1/core/kv_cache_manager.py"]
    pool = files["v1/core/block_pool.py"]
    sched = files["v1/core/sched/scheduler.py"]
    source_open = (
        kv["has_get_block_ids"]
        and kv["has_request_free"]
        and kv["has_coordinator_free"]
        and pool["has_block_pool_free"]
        and sched["has_num_computed_tokens"]
    )
    # Even if source symbols are present, suffix-only release is not safe until
    # the runtime probe proves the invariants below on real block ids.
    gate = "open_for_probe" if source_open else "blocked"
    return {
        "schema_version": "phase10_5_suffix_free_audit_v0",
        "files": files,
        "suffix_free_gate": gate,
        "runtime_invariants": RUNTIME_INVARIANTS,
        "minimum_probe": (
            "Verify prefix physical block ids stay unchanged, suffix physical block ids return to the block pool, "
            "free_gpu_blocks_delta >= suffix_blocks_freed, num_computed_tokens_after == anchor_token_end, and request completion."
            if source_open
            else "Do not patch suffix free; use prefix-cache canonical layout fallback or full-recompute baseline."
        ),
        "notes": "source_gate_only_runtime_invariants_still_required",
    }


def import_vllm_info() -> tuple[Path, str]:
    import vllm

    return Path(vllm.__file__).resolve().parent, importlib.metadata.version("vllm")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vllm-root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/vllm_v1_suffix_free_audit_v0.json"))
    args = parser.parse_args()
    if args.vllm_root:
        root = args.vllm_root
        version = "unknown"
    else:
        root, version = import_vllm_info()
    report = audit_suffix_free_path(root)
    report["vllm_root"] = str(root)
    report["vllm_version"] = version
    report["python_executable"] = sys.executable
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"suffix_free_gate": report["suffix_free_gate"], "vllm_version": version}, sort_keys=True))
    return 0 if report["suffix_free_gate"] == "open_for_probe" else 2


if __name__ == "__main__":
    raise SystemExit(main())
