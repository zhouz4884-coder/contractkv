#!/usr/bin/env python3
"""Audit installed vLLM source for request/block/swap hook points."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from typing import Any


PATTERNS = [
    "scheduler",
    "sequence",
    "sequence_group",
    "block_manager",
    "kv_cache_manager",
    "prefix_cache",
    "swap_in",
    "swap_out",
    "preemption",
    "preempt",
    "block_table",
    "gpu_blocks",
    "cpu_blocks",
    "request_id",
    "physical_block",
    "logical_block",
]


def _line_hits(path: Path, pattern: str, max_hits_per_file: int) -> list[dict[str, Any]]:
    hits = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return hits
    needle = pattern.lower()
    for lineno, line in enumerate(lines, start=1):
        if needle in line.lower():
            hits.append({"line": lineno, "text": line.strip()[:240]})
            if len(hits) >= max_hits_per_file:
                break
    return hits


def scan_source_tree(root: Path, patterns: list[str] | None = None, max_hits_per_file: int = 8) -> dict[str, Any]:
    patterns = patterns or PATTERNS
    files = [p for p in root.rglob("*.py") if p.is_file()]
    result: dict[str, Any] = {}
    for pattern in patterns:
        pattern_files = []
        total_hits = 0
        for path in files:
            hits = _line_hits(path, pattern, max_hits_per_file)
            if not hits:
                continue
            total_hits += len(hits)
            pattern_files.append(
                {
                    "path": str(path.relative_to(root)),
                    "hits": hits,
                }
            )
        result[pattern] = {
            "total_hits": total_hits,
            "files": pattern_files,
        }
    return result


def _has_any(hits: dict[str, Any], *patterns: str) -> bool:
    return any(hits.get(pattern, {}).get("total_hits", 0) > 0 for pattern in patterns)


def _top_files(hits: dict[str, Any], *patterns: str, limit: int = 12) -> list[str]:
    counts: dict[str, int] = {}
    for pattern in patterns:
        for item in hits.get(pattern, {}).get("files", []):
            counts[item["path"]] = counts.get(item["path"], 0) + len(item.get("hits", []))
    return [path for path, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def summarize_hook_points(
    hits: dict[str, Any],
    vllm_root: Path,
    vllm_version: str,
    python_executable: str,
) -> dict[str, Any]:
    request_files = _top_files(hits, "request_id", "sequence", "sequence_group", "scheduler")
    block_files = _top_files(hits, "block_table", "logical_block", "physical_block", "gpu_blocks", "cpu_blocks", "block_manager", "kv_cache_manager")
    swap_files = _top_files(hits, "swap_in", "swap_out", "preempt", "preemption")
    has_request = _has_any(hits, "request_id") and _has_any(hits, "sequence", "sequence_group", "scheduler")
    has_block_index = _has_any(hits, "block_table", "logical_block", "block_manager", "kv_cache_manager")
    has_physical = _has_any(hits, "physical_block", "gpu_blocks", "cpu_blocks", "block_table")
    has_swap = _has_any(hits, "swap_in", "swap_out")
    if has_swap:
        feasibility = "direct_swap_path_present_needs_runtime_validation"
        minimal_path = "Add instrumentation around scheduler/block-manager swap calls, then expose a guarded request-level trigger for sequence/group-level swap."
    else:
        feasibility = "no_direct_swap_symbol_found"
        minimal_path = "Add read-only block table observer first; implement a minimal block migration API only after locating active KV cache manager ownership."
    return {
        "schema_version": "phase10_vllm_hook_audit_v0",
        "python_executable": python_executable,
        "vllm_root": str(vllm_root),
        "vllm_version": vllm_version,
        "patterns": hits,
        "candidate_files": {
            "request_sequence_mapping": request_files,
            "token_block_mapping": block_files,
            "swap_path": swap_files,
        },
        "answers": {
            "request_id_mapping": {
                "status": "likely_available" if has_request else "not_confirmed",
                "evidence_files": request_files,
                "note": "Audit checks source symbols only; runtime object path still needs instrumentation.",
            },
            "prompt_token_span_to_block_index": {
                "status": "likely_available" if has_block_index else "not_confirmed",
                "evidence_files": block_files,
                "note": "Token span can be approximated by block_size; exact mapping needs live block table access.",
            },
            "block_index_to_physical_block_id": {
                "status": "possibly_available" if has_physical else "not_confirmed",
                "evidence_files": block_files,
                "note": "Physical ids require active block table or KV cache manager object access.",
            },
            "swap_in_out_path": {
                "status": "symbols_present" if has_swap else "not_found",
                "evidence_files": swap_files,
                "note": "Symbol presence is not proof that manual request-level swap is safe.",
            },
            "files_to_modify": sorted(set(request_files + block_files + swap_files)),
            "minimal_implementation_path": minimal_path,
            "one_to_two_week_feasibility": "possible_after_runtime_probe" if has_request and has_block_index else "risky_until_mapping_is_confirmed",
            "phase10_3_gate": "open_for_probe_only" if has_swap and has_request else "closed",
            "fallback_if_uncontrollable": "Segment-aware prefix cache real metric using vLLM prefix-cache TTFT and SLO measurements.",
        },
        "feasibility": feasibility,
    }


def import_vllm_info() -> tuple[Path, str]:
    import vllm

    version = importlib.metadata.version("vllm")
    return Path(vllm.__file__).resolve().parent, version


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vllm-root", type=Path, default=None)
    parser.add_argument("--vllm-version", default="")
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/vllm_hook_points_v0.json"))
    args = parser.parse_args()
    if args.vllm_root is None:
        vllm_root, version = import_vllm_info()
    else:
        vllm_root = args.vllm_root.resolve()
        version = args.vllm_version or "unknown"
    hits = scan_source_tree(vllm_root, PATTERNS)
    summary = summarize_hook_points(hits, vllm_root, version, sys.executable)
    write_json(args.output, summary)
    print(f"vllm_root={vllm_root}")
    print(f"vllm_version={version}")
    print(f"phase10_3_gate={summary['answers']['phase10_3_gate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
