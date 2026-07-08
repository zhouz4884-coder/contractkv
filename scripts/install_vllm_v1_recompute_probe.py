#!/usr/bin/env python3
"""Install a guarded vLLM V1 recompute/preemption actuator probe."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


MARKER_BEGIN = "# CONTRACTKV_RECOMPUTE_PROBE_BEGIN"
MARKER_END = "# CONTRACTKV_RECOMPUTE_PROBE_END"
BACKUP_SUFFIX = ".contractkv_recompute_probe.bak"

HELPER = f'''
{MARKER_BEGIN}
def _contractkv_force_preempt_once(scheduler, scheduled_timestamp):
    """Force one real V1 preemption/recompute event when explicitly enabled."""
    import json
    import os
    import time as _contractkv_time

    if os.environ.get("CONTRACTKV_RECOMPUTE_PROBE") != "1":
        return []
    if getattr(scheduler, "_contractkv_recompute_probe_done", False):
        return []
    running = list(getattr(scheduler, "running", []))
    if not running:
        return []
    target_request_id = os.environ.get("CONTRACTKV_RECOMPUTE_TARGET_REQUEST_ID", "")
    try:
        min_computed_tokens = int(os.environ.get("CONTRACTKV_RECOMPUTE_MIN_COMPUTED_TOKENS", "1"))
    except ValueError:
        min_computed_tokens = 1

    selected = None
    for request in running:
        if target_request_id and getattr(request, "request_id", "") != target_request_id:
            continue
        if int(getattr(request, "num_computed_tokens", 0) or 0) >= min_computed_tokens:
            selected = request
            break
    if selected is None:
        return []

    block_pool = getattr(scheduler.kv_cache_manager, "block_pool", None)

    def _free_blocks():
        return int(block_pool.get_num_free_blocks()) if block_pool is not None else 0

    def _block_ids():
        try:
            return scheduler.kv_cache_manager.get_block_ids(selected.request_id)
        except Exception:
            return []

    before_free_gpu_blocks = _free_blocks()
    before_block_ids = _block_ids()
    start = _contractkv_time.perf_counter()
    if selected in scheduler.running:
        scheduler.running.remove(selected)
    scheduler.kv_cache_manager.free(selected)
    scheduler.encoder_cache_manager.free(selected)
    selected.status = RequestStatus.PREEMPTED
    selected.num_computed_tokens = 0
    if getattr(scheduler, "log_stats", False):
        selected.record_event(EngineCoreEventType.PREEMPTED, scheduled_timestamp)
    scheduler.waiting.prepend_request(selected)
    scheduler._contractkv_recompute_probe_done = True
    after_free_gpu_blocks = _free_blocks()
    elapsed_ms = (_contractkv_time.perf_counter() - start) * 1000.0

    event = {{
        "event": "contractkv_forced_recompute_preemption",
        "timestamp": _contractkv_time.time(),
        "request_id": selected.request_id,
        "before_free_gpu_blocks": before_free_gpu_blocks,
        "after_free_gpu_blocks": after_free_gpu_blocks,
        "free_gpu_blocks_delta": after_free_gpu_blocks - before_free_gpu_blocks,
        "before_block_table_length": sum(len(group) for group in before_block_ids) if before_block_ids else 0,
        "preempt_latency_ms": round(elapsed_ms, 6),
    }}
    log_path = os.environ.get("CONTRACTKV_RECOMPUTE_PROBE_LOG")
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
    call = "        preempted_reqs.extend(_contractkv_force_preempt_once(self, scheduled_timestamp))\n"
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
        "        preempted_reqs.extend(_contractkv_force_preempt_once(self, scheduled_timestamp))\n",
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
