#!/usr/bin/env python3
"""Install a guarded vLLM V1 Risk-Anchored Recompute probe."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


MARKER_BEGIN = "# CONTRACTKV_ANCHOR_RECOMPUTE_PROBE_BEGIN"
MARKER_END = "# CONTRACTKV_ANCHOR_RECOMPUTE_PROBE_END"
BACKUP_SUFFIX = ".contractkv_anchor_recompute_probe.bak"

HELPER = f'''
{MARKER_BEGIN}
def _contractkv_anchor_recompute_once(scheduler, scheduled_timestamp):
    """Release suffix KV blocks while retaining prefix blocks under a guard."""
    import json
    import os
    import time as _contractkv_time

    if os.environ.get("CONTRACTKV_ANCHOR_RECOMPUTE_PROBE") != "1":
        return []
    if getattr(scheduler, "_contractkv_anchor_recompute_probe_done", False):
        return []
    running = list(getattr(scheduler, "running", []))
    if not running:
        return []
    try:
        anchor_token_end = int(os.environ.get("CONTRACTKV_ANCHOR_TOKEN_END", "0"))
        boundary_guard_tokens = int(os.environ.get("CONTRACTKV_BOUNDARY_GUARD_TOKENS", "32"))
    except ValueError:
        return []
    if anchor_token_end <= 0:
        return []
    block_size = int(getattr(scheduler.kv_cache_manager, "block_size", 0) or 0)
    if block_size <= 0:
        return []
    anchor_block_end = (anchor_token_end + block_size - 1) // block_size
    target_request_id = os.environ.get("CONTRACTKV_ANCHOR_TARGET_REQUEST_ID", "")

    selected = None
    for request in running:
        if target_request_id and getattr(request, "request_id", "") != target_request_id:
            continue
        if int(getattr(request, "num_computed_tokens", 0) or 0) >= anchor_token_end:
            selected = request
            break
    if selected is None:
        return []

    block_pool = getattr(scheduler.kv_cache_manager, "block_pool", None)
    coordinator = getattr(scheduler.kv_cache_manager, "coordinator", None)
    managers = tuple(getattr(coordinator, "single_type_managers", ()) or ())
    if block_pool is None or not managers:
        return []

    def _free_blocks():
        return int(block_pool.get_num_free_blocks())

    before_free_gpu_blocks = _free_blocks()
    before_groups = []
    after_groups = []
    suffix_groups = []
    prefix_groups = []
    duplicate_block_id_detected = False
    block_table_consistency = True
    start = _contractkv_time.perf_counter()

    try:
        for manager in managers:
            req_blocks = list(manager.req_to_blocks.get(selected.request_id, []))
            if len(req_blocks) <= anchor_block_end:
                block_table_consistency = False
                continue
            prefix = req_blocks[:anchor_block_end]
            suffix = req_blocks[anchor_block_end:]
            before_groups.append([block.block_id for block in req_blocks])
            prefix_groups.append([block.block_id for block in prefix])
            suffix_groups.append([block.block_id for block in suffix])
            manager.req_to_blocks[selected.request_id] = prefix
            manager.num_cached_block[selected.request_id] = min(
                int(manager.num_cached_block.get(selected.request_id, 0)),
                len(prefix),
            )
            manager.block_pool.free_blocks(reversed(suffix))
            after_groups.append([block.block_id for block in manager.req_to_blocks.get(selected.request_id, [])])
        flat_after = [block_id for group in after_groups for block_id in group]
        duplicate_block_id_detected = len(flat_after) != len(set(flat_after))
        prefix_blocks_retained_exact = all(after == prefix for after, prefix in zip(after_groups, prefix_groups))
        suffix_blocks_freed_exact = all(
            not any(block_id in after for block_id in suffix)
            for after, suffix in zip(after_groups, suffix_groups)
        )
        suffix_blocks_freed = sum(len(group) for group in suffix_groups)
        prefix_blocks_retained = sum(len(group) for group in prefix_groups)
        if suffix_blocks_freed <= 0 or not prefix_blocks_retained_exact or not suffix_blocks_freed_exact:
            block_table_consistency = False
    except Exception as exc:
        log_path = os.environ.get("CONTRACTKV_ANCHOR_RECOMPUTE_PROBE_LOG")
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({{
                    "event": "contractkv_anchor_recompute",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:300],
                    "anchored_gate": "exception_before_state_update",
                }}, ensure_ascii=False) + "\\n")
        return []

    if selected in scheduler.running:
        scheduler.running.remove(selected)
    scheduler.encoder_cache_manager.free(selected)
    selected.status = RequestStatus.PREEMPTED
    selected.num_computed_tokens = anchor_token_end
    if getattr(scheduler, "log_stats", False):
        selected.record_event(EngineCoreEventType.PREEMPTED, scheduled_timestamp)
    scheduler.waiting.prepend_request(selected)
    scheduler._contractkv_anchor_recompute_probe_done = True

    after_free_gpu_blocks = _free_blocks()
    event = {{
        "event": "contractkv_anchor_recompute",
        "timestamp": _contractkv_time.time(),
        "request_id": selected.request_id,
        "block_size": block_size,
        "anchor_token_end": anchor_token_end,
        "anchor_block_end": anchor_block_end,
        "recompute_start_token": max(0, anchor_token_end - boundary_guard_tokens),
        "boundary_guard_tokens": boundary_guard_tokens,
        "before_free_gpu_blocks": before_free_gpu_blocks,
        "after_free_gpu_blocks": after_free_gpu_blocks,
        "free_gpu_blocks_delta": after_free_gpu_blocks - before_free_gpu_blocks,
        "prefix_blocks_retained": prefix_blocks_retained,
        "suffix_blocks_freed": suffix_blocks_freed,
        "num_computed_tokens_after": selected.num_computed_tokens,
        "prefix_blocks_before": prefix_groups,
        "prefix_blocks_after": after_groups,
        "suffix_blocks_before": suffix_groups,
        "prefix_blocks_retained_exact": prefix_blocks_retained_exact,
        "suffix_blocks_freed_exact": suffix_blocks_freed_exact,
        "duplicate_block_id_detected": duplicate_block_id_detected,
        "block_table_consistency": block_table_consistency,
        "actuator_latency_ms": round((_contractkv_time.perf_counter() - start) * 1000.0, 6),
    }}
    log_path = os.environ.get("CONTRACTKV_ANCHOR_RECOMPUTE_PROBE_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\\n")
    return [selected]
{MARKER_END}
'''


def _backup_path(path: Path) -> Path:
    return path.with_name(path.name + BACKUP_SUFFIX)


def install(scheduler_path: Path) -> str:
    text = scheduler_path.read_text(encoding="utf-8")
    if MARKER_BEGIN in text:
        return "already_installed"
    backup = _backup_path(scheduler_path)
    if not backup.exists():
        shutil.copy2(scheduler_path, backup)
    class_match = re.search(r"^class Scheduler\b.*:$", text, flags=re.MULTILINE)
    if class_match is None:
        raise ValueError("Could not find class Scheduler in scheduler.py")
    text = text[: class_match.start()] + HELPER + "\n\n" + text[class_match.start() :]
    needle = "        # First, schedule the RUNNING requests."
    call = "        preempted_reqs.extend(_contractkv_anchor_recompute_once(self, scheduled_timestamp))\n"
    if needle not in text:
        raise ValueError("Could not find scheduler running-request section")
    text = text.replace(needle, call + needle, 1)
    scheduler_path.write_text(text, encoding="utf-8", newline="\n")
    return "installed"


def uninstall(scheduler_path: Path) -> str:
    backup = _backup_path(scheduler_path)
    if backup.exists():
        shutil.copy2(backup, scheduler_path)
        return "uninstalled"
    text = scheduler_path.read_text(encoding="utf-8")
    if MARKER_BEGIN not in text:
        return "not_installed"
    start = text.index(MARKER_BEGIN)
    end = text.index(MARKER_END) + len(MARKER_END)
    text = text[:start] + text[end:]
    text = text.replace(
        "        preempted_reqs.extend(_contractkv_anchor_recompute_once(self, scheduled_timestamp))\n",
        "",
        1,
    )
    scheduler_path.write_text(text, encoding="utf-8", newline="\n")
    return "uninstalled_without_backup"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduler", type=Path, required=True)
    parser.add_argument("--action", choices=["install", "uninstall"], default="install")
    args = parser.parse_args()
    status = install(args.scheduler) if args.action == "install" else uninstall(args.scheduler)
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
