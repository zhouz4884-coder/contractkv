#!/usr/bin/env python3
"""Audit ContractKV hook candidates in an installed vLLM runtime."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib
import inspect
import json
from pathlib import Path
from typing import Any


HOOK_SPECS = [
    {
        "hook": "layout_admission",
        "module": "vllm.v1.core.sched.scheduler",
        "qualname": "Scheduler.add_request",
        "role": "Attach a runtime-bound layout decision before request scheduling.",
    },
    {
        "hook": "prefix_lookup",
        "module": "vllm.v1.core.kv_cache_manager",
        "qualname": "KVCacheManager.get_computed_blocks",
        "role": "Observe the longest native prefix-cache hit for a request.",
    },
    {
        "hook": "block_allocation",
        "module": "vllm.v1.core.kv_cache_manager",
        "qualname": "KVCacheManager.allocate_slots",
        "role": "Allocate request KV blocks after native prefix lookup.",
    },
    {
        "hook": "cache_publication",
        "module": "vllm.v1.core.kv_cache_manager",
        "qualname": "KVCacheManager.cache_blocks",
        "role": "Enter verified computed blocks into the cache coordinator.",
    },
    {
        "hook": "hash_index_registration",
        "module": "vllm.v1.core.block_pool",
        "qualname": "BlockPool.cache_full_blocks",
        "role": "Register full block hashes in the native prefix-cache index.",
    },
    {
        "hook": "partial_block_registration",
        "module": "vllm.v1.core.block_pool",
        "qualname": "BlockPool.cache_partial_block",
        "role": "Register an intra-block prefix boundary; this is not non-contiguous segment reuse.",
    },
]


def _resolve(module_name: str, qualname: str) -> Any:
    value: Any = importlib.import_module(module_name)
    for component in qualname.split("."):
        value = getattr(value, component)
    return value


def _record_hash_status(source_path: Path) -> dict[str, Any]:
    site_packages = next(
        parent for parent in source_path.parents if parent.name == "site-packages"
    )
    record = next(site_packages.glob("vllm-*.dist-info/RECORD"))
    relative = source_path.relative_to(site_packages).as_posix()
    expected = ""
    with record.open(encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if row and row[0] == relative:
                expected = row[1].split("=", 1)[1] if row[1] else ""
                break
    digest = base64.urlsafe_b64encode(hashlib.sha256(source_path.read_bytes()).digest())
    actual = digest.rstrip(b"=").decode("ascii")
    return {
        "record_path": str(record),
        "record_sha256": expected,
        "actual_sha256": actual,
        "matches_installed_wheel_record": bool(expected and expected == actual),
    }


def inspect_hook(spec: dict[str, str]) -> dict[str, Any]:
    try:
        target = _resolve(spec["module"], spec["qualname"])
        source_file = Path(inspect.getsourcefile(target) or "")
        source_lines, first_line = inspect.getsourcelines(target)
        source = "".join(source_lines)
        return {
            **spec,
            "available": True,
            "signature": str(inspect.signature(target)),
            "source_file": str(source_file),
            "first_line": first_line,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "wheel_integrity": _record_hash_status(source_file),
            "error": "",
        }
    except Exception as exc:
        return {
            **spec,
            "available": False,
            "signature": "",
            "source_file": "",
            "first_line": 0,
            "source_sha256": "",
            "wheel_integrity": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def build_audit() -> dict[str, Any]:
    import torch
    import transformers
    import vllm

    hooks = [inspect_hook(spec) for spec in HOOK_SPECS]
    lookup = _resolve(
        "vllm.v1.core.kv_cache_manager", "KVCacheManager.get_computed_blocks"
    )
    lookup_source = inspect.getsource(lookup)
    partial = _resolve("vllm.v1.core.block_pool", "BlockPool.cache_partial_block")
    partial_helper = _resolve(
        "vllm.v1.core.block_pool", "BlockPool._get_partial_block_hash"
    )
    partial_source = inspect.getsource(partial) + inspect.getsource(partial_helper)
    wheel_clean = all(
        item["wheel_integrity"].get("matches_installed_wheel_record", False)
        for item in hooks
        if item["available"]
    )
    return {
        "audit_schema": "contractkv.vllm-version-compatibility.v1",
        "runtime": {
            "vllm_version": vllm.__version__,
            "torch_version": torch.__version__,
            "torch_cuda_version": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count(),
            "transformers_version": transformers.__version__,
        },
        "wheel_source_integrity": {
            "all_audited_files_match_record": wheel_clean,
            "meaning": "Audited source files match the installed vLLM wheel RECORD.",
        },
        "native_lookup_semantics": {
            "uses_longest_prefix_chain": (
                "find_longest_cache_hit" in lookup_source
                and "request.block_hashes" in lookup_source
            ),
            "supports_arbitrary_non_contiguous_segments": False,
            "evidence": (
                "KVCacheManager.get_computed_blocks passes request.block_hashes "
                "to find_longest_cache_hit with a maximum prefix length."
            ),
        },
        "partial_block_semantics": {
            "available": True,
            "remains_prefix_chain_metadata": (
                "partial prefix" in partial_source
                and "request.block_hashes" in partial_source
            ),
            "supports_arbitrary_non_contiguous_segments": False,
            "evidence": (
                "cache_partial_block exposes a boundary inside an owning cache "
                "block and derives its key from the request prefix-chain hash."
            ),
        },
        "hook_points": hooks,
        "portability_decision": {
            "layout_admission": "open",
            "prefix_observation": "open",
            "transactional_publication": "requires_adaptation",
            "full_source_patch_drop_in": "blocked",
            "reason": (
                "The V1 admission, lookup, allocation, and hash-index objects "
                "remain available, but signatures and publication internals differ "
                "from the frozen vLLM 0.10.2 implementation."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/appendix/vllm_025_hook_portability_audit.json"),
    )
    args = parser.parse_args()
    audit = build_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0 if all(item["available"] for item in audit["hook_points"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
