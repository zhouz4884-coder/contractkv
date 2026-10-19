#!/usr/bin/env python3
"""Install/uninstall a guarded read-only ContractKV probe into vLLM."""

from __future__ import annotations

import argparse
from pathlib import Path


HELPER_MARKER = "# CONTRACTKV_PROBE_HELPER_BEGIN"
HELPER_END = "# CONTRACTKV_PROBE_HELPER_END"
CALL_MARKER = "# CONTRACTKV_PROBE_CALL"

HELPER = '''
# CONTRACTKV_PROBE_HELPER_BEGIN
def _contractkv_probe_write_event(event):
    import json
    import os
    import time as _time
    if os.environ.get("CONTRACTKV_PROBE") != "1":
        return
    path = os.environ.get("CONTRACTKV_PROBE_LOG")
    if not path:
        return
    event.setdefault("ts", _time.time())
    event.setdefault("source", "vllm.engine.llm_engine")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(event, ensure_ascii=False, default=str) + "\\n")
    except Exception:
        pass


def _contractkv_probe_log_scheduler_iteration(engine, virtual_engine, seq_group_metadata_list, scheduler_outputs):
    import os
    if os.environ.get("CONTRACTKV_PROBE") != "1":
        return
    try:
        scheduler = engine.scheduler[virtual_engine]
        block_manager = getattr(scheduler, "block_manager", None)
        allocator = getattr(block_manager, "block_allocator", None)
        block_size = int(getattr(block_manager, "block_size", 0) or 0)
        free_gpu_blocks = 0
        free_cpu_blocks = 0
        if allocator is not None:
            try:
                free_gpu_blocks = int(allocator.get_num_free_blocks(device=Device.GPU))
            except Exception:
                free_gpu_blocks = 0
            try:
                free_cpu_blocks = int(allocator.get_num_free_blocks(device=Device.CPU))
            except Exception:
                free_cpu_blocks = 0
        total_gpu_blocks = int(getattr(block_manager, "num_total_gpu_blocks", 0) or 0) if block_manager is not None else 0
        total_cpu_blocks = int(getattr(block_manager, "num_total_cpu_blocks", 0) or 0) if block_manager is not None else 0
        used_gpu_blocks = max(0, total_gpu_blocks - free_gpu_blocks) if total_gpu_blocks else 0
        swapped_cpu_blocks = max(0, total_cpu_blocks - free_cpu_blocks) if total_cpu_blocks else 0
        request_ids = []
        for metadata in seq_group_metadata_list or []:
            request_id = getattr(metadata, "request_id", "")
            request_ids.append(request_id)
            block_tables = getattr(metadata, "block_tables", {}) or {}
            seq_ids = list(block_tables.keys())
            physical_ids = []
            for ids in block_tables.values():
                try:
                    physical_ids.extend(list(ids))
                except Exception:
                    pass
            seq_group = getattr(engine, "seq_id_to_seq_group", {}).get(request_id)
            prompt_token_count = 0
            if seq_group is not None:
                try:
                    seqs = seq_group.get_seqs()
                    if seqs:
                        prompt_token_count = int(seqs[0].get_prompt_len())
                except Exception:
                    prompt_token_count = 0
            _contractkv_probe_write_event({
                "event": "sequence_group_state",
                "virtual_engine": virtual_engine,
                "request_id": request_id,
                "seq_ids": seq_ids,
                "prompt_token_count": prompt_token_count,
                "block_size": block_size,
                "logical_block_table_length": max((len(v) for v in block_tables.values()), default=0),
                "physical_block_ids": physical_ids[:256],
                "num_physical_block_ids_total": len(physical_ids),
                "free_gpu_blocks": free_gpu_blocks,
                "used_gpu_blocks": used_gpu_blocks,
                "free_cpu_blocks": free_cpu_blocks,
                "swapped_cpu_blocks": swapped_cpu_blocks,
            })
        _contractkv_probe_write_event({
            "event": "scheduler_output",
            "virtual_engine": virtual_engine,
            "request_id": request_ids[0] if len(request_ids) == 1 else ",".join(request_ids),
            "request_ids": request_ids,
            "blocks_to_swap_in": list(getattr(scheduler_outputs, "blocks_to_swap_in", []) or []),
            "blocks_to_swap_out": list(getattr(scheduler_outputs, "blocks_to_swap_out", []) or []),
            "blocks_to_copy": list(getattr(scheduler_outputs, "blocks_to_copy", []) or []),
            "num_prefill_groups": int(getattr(scheduler_outputs, "num_prefill_groups", 0) or 0),
            "num_batched_tokens": int(getattr(scheduler_outputs, "num_batched_tokens", 0) or 0),
            "running_queue_size": int(getattr(scheduler_outputs, "running_queue_size", 0) or 0),
        })
    except Exception as exc:
        _contractkv_probe_write_event({"event": "probe_error", "error": repr(exc)})
# CONTRACTKV_PROBE_HELPER_END
'''

CALL = f'''            {CALL_MARKER}
            _contractkv_probe_log_scheduler_iteration(
                self, virtual_engine, seq_group_metadata_list,
                scheduler_outputs)
'''


def install(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    backup = path.with_suffix(path.suffix + ".contractkv_probe.bak")
    if HELPER_MARKER in text:
        return "already_installed"
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    text = text.replace("logger = init_logger(__name__)\n_LOCAL_LOGGING_INTERVAL_SEC = 5\n", "logger = init_logger(__name__)\n_LOCAL_LOGGING_INTERVAL_SEC = 5\n" + HELPER + "\n", 1)
    needle = "            ctx.scheduler_outputs = scheduler_outputs\n\n"
    if needle not in text:
        raise RuntimeError("Could not find scheduler output assignment insertion point.")
    text = text.replace(needle, "            ctx.scheduler_outputs = scheduler_outputs\n" + CALL + "\n", 1)
    path.write_text(text, encoding="utf-8")
    return "installed"


def uninstall(path: Path) -> str:
    backup = path.with_suffix(path.suffix + ".contractkv_probe.bak")
    if backup.exists():
        path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        return "restored_from_backup"
    text = path.read_text(encoding="utf-8")
    if HELPER_MARKER not in text:
        return "not_installed"
    start = text.index(HELPER_MARKER)
    end = text.index(HELPER_END) + len(HELPER_END)
    text = text[:start] + text[end:]
    call_start = text.index(f"            {CALL_MARKER}")
    call_end = text.index("\n\n", call_start)
    text = text[:call_start] + text[call_end + 2 :]
    path.write_text(text, encoding="utf-8")
    return "uninstalled_without_backup"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-engine", type=Path, required=True)
    parser.add_argument("--action", choices=["install", "uninstall"], default="install")
    args = parser.parse_args()
    status = install(args.llm_engine) if args.action == "install" else uninstall(args.llm_engine)
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
