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

HELPER = r'''
# CONTRACTKV_PREFIX_METRICS_HELPER_BEGIN
_contractkv_prefix_metric_seen = set()


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


def _contractkv_prefix_metrics_log_scheduler(scheduler, scheduler_output):
    import os
    import time as _time
    if os.environ.get("CONTRACTKV_PREFIX_METRICS") != "1":
        return
    try:
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
            remaining_prompt = max(0, prompt_tokens - computed_before)
            prefill_scheduled_tokens = min(scheduled_tokens, remaining_prompt)
            prefix_hit_tokens = min(prompt_tokens, computed_before) if initial else None
            physical_ids = _contractkv_prefix_metrics_block_ids(scheduler, request_id)
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
                "physical_block_ids": physical_ids[:256],
                "physical_block_count": len(physical_ids),
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


def install(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if HELPER_BEGIN in text:
        return "already_installed"
    anchor = "class Scheduler"
    if anchor not in text:
        raise RuntimeError("Could not find V1 Scheduler class anchor.")
    text = text.replace(anchor, HELPER + "\n\n" + anchor, 1)
    needle = "        self._update_after_schedule(scheduler_output)\n"
    if needle not in text:
        raise RuntimeError("Could not find V1 scheduler post-schedule insertion point.")
    text = text.replace(needle, CALL + needle, 1)
    path.write_text(text, encoding="utf-8")
    return "installed"


def uninstall(path: Path) -> str:
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
