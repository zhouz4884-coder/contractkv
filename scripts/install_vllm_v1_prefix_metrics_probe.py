#!/usr/bin/env python3
"""Install a guarded, read-only per-request prefix-cache probe in vLLM V1.

The probe is deliberately scheduler-local.  It reports only facts that the V1
scheduler can observe, and marks worker/GPU-timing or eviction counters as
unavailable rather than inventing values.  It coexists with the earlier
ContractKV runtime and RAR probes.
"""

from __future__ import annotations

import argparse
from pathlib import Path


HELPER_BEGIN = "# CONTRACTKV_PREFIX_METRICS_HELPER_BEGIN"
HELPER_END = "# CONTRACTKV_PREFIX_METRICS_HELPER_END"
CALL_BEGIN = "# CONTRACTKV_PREFIX_METRICS_CALL_BEGIN"
CALL_END = "# CONTRACTKV_PREFIX_METRICS_CALL_END"
BACKUP_SUFFIX = ".contractkv-prefix-metrics.bak"

HELPER = r'''
# CONTRACTKV_PREFIX_METRICS_HELPER_BEGIN
_contractkv_prefix_metric_seen = set()
_contractkv_prefix_query_seen = None
_contractkv_prefix_query_signature = None
_contractkv_prefix_query_epoch = 0


def _contractkv_prefix_metrics_write(event):
    import json
    import os
    import time as _time
    if os.environ.get("CONTRACTKV_PREFIX_METRICS") != "1":
        return
    path = os.environ.get("CONTRACTKV_PREFIX_METRICS_LOG")
    if not path:
        return
    event.setdefault("ts", _time.time())
    event.setdefault("source", "vllm.v1.core.sched.scheduler")
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Instrumentation must never affect serving.
        pass


def _contractkv_prefix_metrics_block_ids(scheduler, request_id):
    try:
        groups = scheduler.kv_cache_manager.get_block_ids(request_id)
        return [block_id for group in groups for block_id in group]
    except Exception:
        return []


def _contractkv_prefix_metrics_block_state(scheduler, block_ids):
    try:
        block_pool = scheduler.kv_cache_manager.block_pool
        refcounts = []
        hashes = []
        resident = []
        for block_id in block_ids:
            block = block_pool.blocks[int(block_id)]
            refcounts.append(int(block.ref_cnt))
            block_hash = getattr(block, "block_hash", None)
            hashes.append(bytes(block_hash).hex() if block_hash is not None else None)
            resident.append(block_hash is not None)
        return refcounts, hashes, resident
    except Exception:
        return [], [], []


def _contractkv_prefix_metrics_process_query(scheduler):
    """Answer read-only candidate residency queries from the layout compiler."""
    import json
    import os
    import time as _time
    global _contractkv_prefix_query_seen
    global _contractkv_prefix_query_signature
    global _contractkv_prefix_query_epoch
    query_path = os.environ.get("CONTRACTKV_PREFIX_QUERY_PATH")
    result_path = os.environ.get("CONTRACTKV_PREFIX_QUERY_RESULT_PATH")
    if not query_path or not result_path or not os.path.exists(query_path):
        return
    try:
        with open(query_path, encoding="utf-8") as handle:
            query = json.load(handle)
        query_id = str(query.get("query_id", ""))
        if not query_id or query_id == _contractkv_prefix_query_seen:
            return
        pool = scheduler.kv_cache_manager.block_pool
        resident = {bytes(key).hex() for key in pool.cached_block_hash_to_block}
        signature = hash(frozenset(resident))
        if signature != _contractkv_prefix_query_signature:
            _contractkv_prefix_query_epoch += 1
            _contractkv_prefix_query_signature = signature
        candidates = []
        for candidate in query.get("candidates", []):
            hashes = [str(item) for item in candidate.get("block_hashes", []) if item]
            matched = 0
            for block_hash in hashes:
                if block_hash not in resident:
                    break
                matched += 1
            candidates.append({
                "candidate_id": str(candidate.get("candidate_id", "")),
                "resident_prefix_blocks": matched,
                "candidate_blocks": len(hashes),
            })
        result = {
            "query_id": query_id,
            "timestamp": _time.time(),
            "cache_epoch": _contractkv_prefix_query_epoch,
            "resident_hash_entries": len(resident),
            "free_gpu_blocks": int(pool.get_num_free_blocks()),
            "candidates": candidates,
        }
        temporary = result_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(result, handle)
        os.replace(temporary, result_path)
        _contractkv_prefix_query_seen = query_id
        _contractkv_prefix_metrics_write({
            "event": "prefix_cache_candidate_residency_query", **result,
        })
    except Exception as exc:
        _contractkv_prefix_metrics_write({
            "event": "prefix_cache_candidate_query_error", "error": repr(exc),
        })


def _contractkv_prefix_metrics_log_scheduler(scheduler, scheduler_output):
    import os
    import time as _time
    if os.environ.get("CONTRACTKV_PREFIX_METRICS") != "1":
        return
    try:
        _contractkv_prefix_metrics_process_query(scheduler)
        block_pool = getattr(getattr(scheduler, "kv_cache_manager", None), "block_pool", None)
        block_size = int(getattr(scheduler, "block_size", 0) or 0)
        scheduled = getattr(scheduler_output, "num_scheduled_tokens", {}) or {}
        for request_id, scheduled_tokens in scheduled.items():
            request = getattr(scheduler, "requests", {}).get(request_id)
            if request is None:
                continue
            prompt_tokens = int(getattr(request, "num_prompt_tokens", 0) or 0)
            if not prompt_tokens:
                prompt_tokens = len(getattr(request, "prompt_token_ids", []) or [])
            computed_before = int(getattr(request, "num_computed_tokens", 0) or 0)
            scheduled_tokens = int(scheduled_tokens or 0)
            initial = request_id not in _contractkv_prefix_metric_seen
            if initial:
                _contractkv_prefix_metric_seen.add(request_id)
            if (os.environ.get("CONTRACTKV_PREFIX_INITIAL_ONLY") == "1"
                    and not initial):
                continue
            remaining_prompt = max(0, prompt_tokens - computed_before)
            prefill_scheduled_tokens = min(scheduled_tokens, remaining_prompt)
            prefix_hit_tokens = min(prompt_tokens, computed_before) if initial else None
            physical_ids = _contractkv_prefix_metrics_block_ids(scheduler, request_id)
            block_refcounts, block_hashes, block_cache_resident = (
                _contractkv_prefix_metrics_block_state(scheduler, physical_ids))
            # These are scheduler-observable derivations, not hidden cache-manager counters.
            reused_blocks = (prefix_hit_tokens // block_size) if initial and block_size else None
            allocated_blocks = max(0, len(physical_ids) - (reused_blocks or 0))
            arrival = getattr(request, "arrival_time", None)
            wait_ms = None
            if initial and isinstance(arrival, (int, float)):
                candidate = (_time.time() - float(arrival)) * 1000.0
                if 0.0 <= candidate <= 3_600_000.0:
                    wait_ms = candidate
            _contractkv_prefix_metrics_write({
                "event": "prefix_cache_request_observation",
                "request_id": request_id,
                "initial_prefill_observation": initial,
                "prompt_tokens": prompt_tokens,
                "prefix_lookup_tokens": prompt_tokens if initial else None,
                "prefix_hit_tokens": prefix_hit_tokens,
                "new_prefill_tokens_this_iteration": prefill_scheduled_tokens,
                "num_computed_tokens_before_schedule": computed_before,
                "scheduled_tokens": scheduled_tokens,
                "block_size": block_size,
                "physical_block_ids": physical_ids[:1024],
                "physical_block_count": len(physical_ids),
                "physical_block_refcounts": block_refcounts[:1024],
                "physical_block_hashes": block_hashes[:1024],
                "physical_block_cache_resident": block_cache_resident[:1024],
                "reused_physical_blocks": reused_blocks,
                "reused_physical_blocks_method": "derived_floor(prefix_hit_tokens/block_size)",
                "newly_allocated_blocks": allocated_blocks,
                "newly_allocated_blocks_method": "observed_block_table_minus_derived_reused_blocks",
                "prefix_cache_evictions": None,
                "prefix_cache_evictions_availability": "unavailable_in_scheduler_probe",
                "scheduler_wait_ms": wait_ms,
                "prefill_gpu_ms": None,
                "decode_gpu_ms": None,
                "gpu_timing_availability": "requires_worker_or_metrics_endpoint_probe",
                "free_gpu_blocks": int(block_pool.get_num_free_blocks()) if block_pool is not None else None,
                "total_gpu_blocks": int(getattr(block_pool, "num_gpu_blocks", 0) or 0) if block_pool is not None else None,
                "used_gpu_blocks": (int(getattr(block_pool, "num_gpu_blocks", 0) or 0)
                                    - int(block_pool.get_num_free_blocks())) if block_pool is not None else None,
                "cached_physical_entries": sum(len(blocks) for blocks in block_pool.cached_block_hash_to_block.values()) if block_pool is not None else None,
                "scheduler_running_requests": len(getattr(scheduler, "running", []) or []),
                "scheduler_waiting_requests": len(getattr(scheduler, "waiting", []) or []),
            })
        if os.environ.get("CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS") == "1":
            # The snapshot is intentionally scheduler-local: a shared ID is
            # counted only when it is present in multiple *currently active*
            # request block tables, ruling out temporal ID reuse.
            active = getattr(scheduler, "requests", {}) or {}
            owners = {}
            for active_request_id in active:
                for block_id in _contractkv_prefix_metrics_block_ids(scheduler, active_request_id):
                    owners.setdefault(int(block_id), set()).add(str(active_request_id))
            shared_ids = sorted(block_id for block_id, request_ids in owners.items() if len(request_ids) > 1)
            refcounts, _, _ = _contractkv_prefix_metrics_block_state(scheduler, shared_ids)
            _contractkv_prefix_metrics_write({
                "event": "prefix_cache_concurrent_snapshot",
                "active_request_count": len(active),
                "shared_block_ids": shared_ids[:4096],
                "shared_block_request_counts": [len(owners[block_id]) for block_id in shared_ids[:4096]],
                "shared_block_refcounts": refcounts[:4096],
                "free_gpu_blocks": int(block_pool.get_num_free_blocks()) if block_pool is not None else None,
                "total_gpu_blocks": int(getattr(block_pool, "num_gpu_blocks", 0) or 0) if block_pool is not None else None,
            })
    except Exception as exc:
        _contractkv_prefix_metrics_write({"event": "prefix_cache_probe_error", "error": repr(exc)})
# CONTRACTKV_PREFIX_METRICS_HELPER_END
'''

CALL = f'''        {CALL_BEGIN}
        _contractkv_prefix_metrics_log_scheduler(self, scheduler_output)
        {CALL_END}
'''


def _remove_marked_region(text: str, begin: str, end: str) -> str:
    start = text.index(begin)
    finish = text.index(end, start) + len(end)
    return text[:start] + text[finish:]


def _backup_path(path: Path) -> Path:
    return path.with_name(path.name + BACKUP_SUFFIX)


def install(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    original_text = text
    backup = _backup_path(path)
    if HELPER_BEGIN in text:
        text = _remove_marked_region(text, HELPER_BEGIN, HELPER_END)
        anchor = "class Scheduler"
        text = text.replace(anchor, HELPER + "\n\n" + anchor, 1)
        path.write_text(text, encoding="utf-8")
        return "updated"
    anchor = "class Scheduler"
    if anchor not in text:
        raise RuntimeError("Could not find V1 Scheduler class anchor.")
    text = text.replace(anchor, HELPER + "\n\n" + anchor, 1)
    needle = "        self._update_after_schedule(scheduler_output)\n"
    if needle not in text:
        raise RuntimeError("Could not find V1 scheduler post-schedule insertion point.")
    if not backup.exists():
        backup.write_text(original_text, encoding="utf-8")
    text = text.replace(needle, CALL + needle, 1)
    path.write_text(text, encoding="utf-8")
    return "installed"


def uninstall(path: Path) -> str:
    backup = _backup_path(path)
    if backup.exists():
        path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        backup.unlink()
        return "uninstalled"
    text = path.read_text(encoding="utf-8")
    if HELPER_BEGIN not in text:
        return "not_installed"
    text = _remove_marked_region(text, HELPER_BEGIN, HELPER_END)
    text = _remove_marked_region(text, CALL_BEGIN, CALL_END)
    path.write_text(text, encoding="utf-8")
    return "uninstalled"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduler", type=Path, required=True)
    parser.add_argument("--action", choices=["install", "uninstall"], default="install")
    args = parser.parse_args()
    print(install(args.scheduler) if args.action == "install" else uninstall(args.scheduler))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
