#!/usr/bin/env python3
"""Audit vLLM V1 source for ContractKV-controllable actuator candidates."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any


ACTUATOR_NAMES = [
    "active_swap",
    "preemption_recompute",
    "prefix_cache_layout",
    "admission_gate",
]

FOCUS_FILES = [
    "v1/core/sched/scheduler.py",
    "v1/core/kv_cache_manager.py",
    "v1/core/block_pool.py",
    "v1/worker/gpu_model_runner.py",
    "engine/async_llm_engine.py",
    "worker/worker.py",
]

PATTERNS = {
    "swap": ["swap_in", "swap_out", "blocks_to_swap_in", "blocks_to_swap_out", "cpu_blocks"],
    "preemption": ["preempt", "preempted", "recompute", "free", "free_blocks", "block_pool"],
    "prefix": ["prefix_cache", "enable_prefix_caching", "prefix", "cache_hit", "cache_stats"],
    "admission": ["add_request", "abort_request", "waiting", "running", "max_num_seqs", "request_id"],
    "worker_copy": ["copy_blocks", "swap_blocks", "cache_swap", "swap_in", "swap_out"],
    "block_control": ["get_block_ids", "block_table", "get_num_free_blocks", "free_block", "free_blocks"],
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return ""


def _line_hits(path: Path, patterns: list[str], max_hits: int = 12) -> list[dict[str, Any]]:
    text = _read(path)
    if not text:
        return []
    needles = [pattern.lower() for pattern in patterns]
    hits = []
    skip_contractkv_block = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        if "contractkv" in lowered:
            if line.lstrip().startswith("def "):
                skip_contractkv_block = True
            continue
        if skip_contractkv_block:
            if line.startswith((" ", "\t")) or not line.strip():
                continue
            skip_contractkv_block = False
        if any(needle in lowered for needle in needles):
            hits.append({"line": lineno, "text": line.strip()[:240]})
            if len(hits) >= max_hits:
                break
    return hits


def scan_focus_files(vllm_root: Path) -> dict[str, Any]:
    files = {}
    for rel in FOCUS_FILES:
        path = vllm_root / rel
        files[rel] = {
            "exists": path.exists(),
            "hits": {name: _line_hits(path, patterns) for name, patterns in PATTERNS.items()},
        }
    return files


def _files_with_hits(scanned: dict[str, Any], pattern_group: str) -> list[str]:
    return [
        rel
        for rel, item in scanned.items()
        if item["exists"] and item["hits"].get(pattern_group)
    ]


def _has(scanned: dict[str, Any], pattern_group: str, rel_contains: str | None = None) -> bool:
    for rel, item in scanned.items():
        if rel_contains and rel_contains not in rel:
            continue
        if item["exists"] and item["hits"].get(pattern_group):
            return True
    return False


def build_actuator_candidates(scanned: dict[str, Any]) -> dict[str, dict[str, Any]]:
    swap_scheduler = _has(scanned, "swap", "scheduler.py")
    swap_worker = _has(scanned, "worker_copy", "worker") or _has(scanned, "worker_copy", "gpu_model_runner.py")
    recompute_scheduler = _has(scanned, "preemption", "scheduler.py")
    recompute_kv = _has(scanned, "preemption", "kv_cache_manager.py") or _has(scanned, "block_control", "kv_cache_manager.py")
    prefix_available = _has(scanned, "prefix")
    admission_available = _has(scanned, "admission", "async_llm_engine.py") or _has(scanned, "admission", "scheduler.py")

    active_swap_decision = "blocked"
    active_swap_trigger = "blocked"
    active_swap_risk = "high"
    if swap_scheduler and swap_worker:
        active_swap_decision = "probe_later"
        active_swap_trigger = "unknown"
        active_swap_risk = "high"
    elif swap_scheduler:
        active_swap_decision = "do_not_probe_next"
        active_swap_trigger = "blocked"

    recompute_decision = "probe_next" if recompute_scheduler and recompute_kv else "blocked"
    recompute_trigger = "unknown" if recompute_decision == "probe_next" else "blocked"

    prefix_decision = "fallback_probe" if prefix_available else "blocked"
    admission_decision = "auxiliary" if admission_available else "blocked"

    return {
        "active_swap": {
            "actuator": "active_swap",
            "files": sorted(set(_files_with_hits(scanned, "swap") + _files_with_hits(scanned, "worker_copy"))),
            "call_path": "scheduler swap fields -> executor/worker cache copy path -> KV cache manager",
            "can_observe": swap_scheduler,
            "can_trigger": active_swap_trigger,
            "risk": active_swap_risk,
            "minimum_probe": "Locate a real worker cache copy interface before attempting active swap_out/swap_in.",
            "decision": active_swap_decision,
        },
        "preemption_recompute": {
            "actuator": "preemption_recompute",
            "files": sorted(set(_files_with_hits(scanned, "preemption") + _files_with_hits(scanned, "block_control"))),
            "call_path": "scheduler pressure/preemption decision -> kv_cache_manager free/recompute state -> block_pool counters",
            "can_observe": recompute_scheduler or recompute_kv,
            "can_trigger": recompute_trigger,
            "risk": "medium" if recompute_decision == "probe_next" else "high",
            "minimum_probe": "Add a guarded request-level preemption/recompute marker and verify free_gpu_blocks increases while the request completes.",
            "decision": recompute_decision,
        },
        "prefix_cache_layout": {
            "actuator": "prefix_cache_layout",
            "files": _files_with_hits(scanned, "prefix"),
            "call_path": "OpenAI request prompt layout -> vLLM prefix cache -> prefill TTFT",
            "can_observe": prefix_available,
            "can_trigger": "yes" if prefix_available else "blocked",
            "risk": "low" if prefix_available else "medium",
            "minimum_probe": "Replay raw-order and canonical-layout prompts with prefix caching enabled and compare TTFT/p95/output score.",
            "decision": prefix_decision,
        },
        "admission_gate": {
            "actuator": "admission_gate",
            "files": _files_with_hits(scanned, "admission"),
            "call_path": "OpenAI request wrapper -> ContractKV risk/block-pressure gate -> vLLM add_request/defer",
            "can_observe": admission_available,
            "can_trigger": "yes" if admission_available else "blocked",
            "risk": "low",
            "minimum_probe": "Use real risk summary and observed block pressure to admit or defer before forwarding to vLLM.",
            "decision": admission_decision,
        },
    }


def classify_actuator_decisions(actuators: dict[str, dict[str, Any]]) -> dict[str, str]:
    def status(name: str) -> str:
        candidate = actuators[name]
        if candidate["decision"] in {"probe_next", "fallback_probe", "auxiliary"}:
            return "open"
        if candidate["decision"] in {"blocked", "do_not_probe_next"}:
            return "blocked"
        return "unknown"

    return {
        "active_swap": status("active_swap"),
        "active_recompute_preemption": status("preemption_recompute"),
        "prefix_cache_layout": status("prefix_cache_layout"),
        "admission_gate": status("admission_gate"),
    }


def choose_recommended_probe(actuators: dict[str, dict[str, Any]]) -> str:
    for name in ["preemption_recompute", "prefix_cache_layout", "admission_gate", "active_swap"]:
        if actuators[name]["decision"] in {"probe_next", "fallback_probe", "auxiliary", "probe_later"}:
            return name
    return "none"


def audit_v1_actuators(vllm_root: Path, vllm_version: str, python_executable: str) -> dict[str, Any]:
    scanned = scan_focus_files(vllm_root)
    actuators = build_actuator_candidates(scanned)
    decisions = classify_actuator_decisions(actuators)
    return {
        "schema_version": "phase10_4_vllm_v1_actuator_candidates_v0",
        "python_executable": python_executable,
        "vllm_root": str(vllm_root),
        "vllm_version": vllm_version,
        "focus_files": FOCUS_FILES,
        "scanned_files": scanned,
        "actuators": actuators,
        "decisions": decisions,
        "recommended_10_4b_probe": choose_recommended_probe(actuators),
    }


def import_vllm_info() -> tuple[Path, str]:
    import vllm

    version = importlib.metadata.version("vllm")
    return Path(vllm.__file__).resolve().parent, version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vllm-root", type=Path, default=None)
    parser.add_argument("--vllm-version", default="")
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/vllm_v1_actuator_candidates.json"))
    args = parser.parse_args()
    if args.vllm_root is None:
        vllm_root, version = import_vllm_info()
    else:
        vllm_root = args.vllm_root.resolve()
        version = args.vllm_version or "unknown"
    report = audit_v1_actuators(vllm_root, version, sys.executable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"vllm_root={vllm_root}")
    print(f"vllm_version={version}")
    print(f"recommended_10_4b_probe={report['recommended_10_4b_probe']}")
    print(json.dumps(report["decisions"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
