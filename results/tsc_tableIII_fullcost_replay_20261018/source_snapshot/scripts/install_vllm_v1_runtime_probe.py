#!/usr/bin/env python3
"""Install/uninstall a guarded read-only ContractKV probe into vLLM V1 scheduler."""

from __future__ import annotations

import argparse
from pathlib import Path


HELPER_MARKER = "# CONTRACTKV_V1_PROBE_HELPER_BEGIN"
HELPER_END = "# CONTRACTKV_V1_PROBE_HELPER_END"
CALL_MARKER = "# CONTRACTKV_V1_PROBE_CALL"

HELPER = '''
# CONTRACTKV_V1_PROBE_HELPER_BEGIN
def _contractkv_v1_probe_write_event(event):
    import json
    import os
    import time as _time
    if os.environ.get("CONTRACTKV_PROBE") != "1":
        return
    path = os.environ.get("CONTRACTKV_PROBE_LOG")
    if not path:
        return
    event.setdefault("ts", _time.time())
    event.setdefault("source", "vllm.v1.core.sched.scheduler")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(event, ensure_ascii=False, default=str) + "\\n")
    except Exception:
        pass


def _contractkv_v1_probe_log_scheduler(scheduler, scheduler_output, preempted_reqs):
    import os
    if os.environ.get("CONTRACTKV_PROBE") != "1":
        return
    try:
        block_pool = getattr(scheduler.kv_cache_manager, "block_pool", None)
        free_gpu_blocks = int(block_pool.get_num_free_blocks()) if block_pool is not None else 0
        total_gpu_blocks = int(getattr(block_pool, "num_gpu_blocks", 0) or 0) if block_pool is not None else 0
        used_gpu_blocks = max(0, total_gpu_blocks - free_gpu_blocks) if total_gpu_blocks else 0
        block_size = int(getattr(scheduler, "block_size", 0) or 0)
        scheduled_req_ids = list(getattr(scheduler_output, "num_scheduled_tokens", {}).keys())
        for request_id in scheduled_req_ids:
            request = scheduler.requests.get(request_id)
            physical_ids = []
            try:
                for group_ids in scheduler.kv_cache_manager.get_block_ids(request_id):
                    physical_ids.extend(list(group_ids))
            except Exception:
                physical_ids = []
            prompt_token_count = int(getattr(request, "num_prompt_tokens", 0) or 0) if request is not None else 0
            if prompt_token_count == 0 and request is not None:
                prompt_token_count = len(getattr(request, "prompt_token_ids", []) or [])
            _contractkv_v1_probe_write_event({
                "event": "sequence_group_state",
                "engine_version": "v1",
                "request_id": request_id,
                "seq_ids": [request_id],
                "prompt_token_count": prompt_token_count,
                "block_size": block_size,
                "logical_block_table_length": len(physical_ids),
                "physical_block_ids": physical_ids[:256],
                "num_physical_block_ids_total": len(physical_ids),
                "free_gpu_blocks": free_gpu_blocks,
                "used_gpu_blocks": used_gpu_blocks,
                "free_cpu_blocks": 0,
                "swapped_cpu_blocks": 0,
            })
        _contractkv_v1_probe_write_event({
            "event": "scheduler_output",
            "engine_version": "v1",
            "request_id": scheduled_req_ids[0] if len(scheduled_req_ids) == 1 else ",".join(scheduled_req_ids),
            "request_ids": scheduled_req_ids,
            "blocks_to_swap_in": [],
            "blocks_to_swap_out": [],
            "blocks_to_copy": [],
            "num_preempted": len(preempted_reqs),
            "preempted_request_ids": [req.request_id for req in preempted_reqs],
            "total_num_scheduled_tokens": int(getattr(scheduler_output, "total_num_scheduled_tokens", 0) or 0),
            "free_gpu_blocks": free_gpu_blocks,
            "used_gpu_blocks": used_gpu_blocks,
        })
    except Exception as exc:
        _contractkv_v1_probe_write_event({"event": "probe_error", "error": repr(exc)})
# CONTRACTKV_V1_PROBE_HELPER_END
'''

CALL = f'''        {CALL_MARKER}
        _contractkv_v1_probe_log_scheduler(
            self, scheduler_output, preempted_reqs)
'''


def install(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    backup = path.with_suffix(path.suffix + ".contractkv_v1_probe.bak")
    if HELPER_MARKER in text:
        return "already_installed"
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    text = text.replace("logger = init_logger(__name__)\n\n\nclass Scheduler", "logger = init_logger(__name__)\n" + HELPER + "\n\nclass Scheduler", 1)
    needle = "        self._update_after_schedule(scheduler_output)\n        return scheduler_output\n"
    if needle not in text:
        raise RuntimeError("Could not find V1 scheduler return insertion point.")
    text = text.replace(needle, CALL + "        self._update_after_schedule(scheduler_output)\n        return scheduler_output\n", 1)
    path.write_text(text, encoding="utf-8")
    return "installed"


def uninstall(path: Path) -> str:
    backup = path.with_suffix(path.suffix + ".contractkv_v1_probe.bak")
    if backup.exists():
        path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        return "restored_from_backup"
    return "backup_missing"


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
