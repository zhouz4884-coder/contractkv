#!/usr/bin/env python3
"""Install an opt-in micro-chunk + ephemeral-cache hook in vLLM V1."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


HELPER_BEGIN = "# CONTRACTKV_EPHEMERAL_SHADOW_HELPER_BEGIN"
HELPER_END = "# CONTRACTKV_EPHEMERAL_SHADOW_HELPER_END"
RUNNING_BEGIN = "# CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_BEGIN"
RUNNING_END = "# CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_END"
FINALIZE_CALL = "# CONTRACTKV_EPHEMERAL_SHADOW_FINALIZE_CALL"
WAITING_BEGIN = "# CONTRACTKV_EPHEMERAL_SHADOW_WAITING_BEGIN"
WAITING_END = "# CONTRACTKV_EPHEMERAL_SHADOW_WAITING_END"

HELPER = r'''# CONTRACTKV_EPHEMERAL_SHADOW_HELPER_BEGIN
def _contractkv_shadow_enabled(request):
    import os
    return (os.environ.get("CONTRACTKV_EPHEMERAL_SHADOW") == "1"
            and "contractkv-shadow-" in str(getattr(request, "request_id", "")))


def _contractkv_shadow_write(event):
    import json
    import os
    import time as _time
    path = os.environ.get("CONTRACTKV_EPHEMERAL_SHADOW_LOG")
    if not path:
        return
    event.setdefault("timestamp", _time.time())
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _contractkv_shadow_has_foreground_work(scheduler, current_request):
    waiting = any(not _contractkv_shadow_enabled(req) for req in scheduler.waiting)
    running = any(
        req is not current_request and not _contractkv_shadow_enabled(req)
        for req in scheduler.running
    )
    return waiting or running


def _contractkv_shadow_chunk_tokens(request):
    import os
    if not _contractkv_shadow_enabled(request):
        return None
    try:
        return max(1, int(os.environ.get("CONTRACTKV_SHADOW_CHUNK_TOKENS", "32")))
    except ValueError:
        return 32


def _contractkv_shadow_cache_entries(pool):
    return sum(len(blocks) for blocks in pool.cached_block_hash_to_block.values())


def _contractkv_shadow_finalize(scheduler, request):
    import os
    import time as _time
    if not _contractkv_shadow_enabled(request):
        return
    pool = scheduler.kv_cache_manager.block_pool
    request_id = str(request.request_id)
    blocks = scheduler.kv_cache_manager.get_blocks(request_id)
    physical_blocks = [block for group in blocks.blocks for block in group]
    visible_before = sum(block.block_hash is not None for block in physical_blocks)
    cache_before = _contractkv_shadow_cache_entries(pool)
    free_before = pool.get_num_free_blocks()
    action = "abort" if "-abort-" in request_id else "commit"
    started = _time.perf_counter()
    stable_tokens = min(
        int(getattr(request, "num_prompt_tokens", 0) or 0),
        int(getattr(request, "num_computed_tokens", 0) or 0),
    )
    if action == "commit" and stable_tokens > 0:
        scheduler.kv_cache_manager.cache_blocks(request, stable_tokens)
    elapsed_ms = (_time.perf_counter() - started) * 1000.0
    visible_after = sum(block.block_hash is not None for block in physical_blocks)
    _contractkv_shadow_write({
        "event": "ephemeral_finalize",
        "request_id": request_id,
        "action": action,
        "stable_tokens": stable_tokens,
        "physical_blocks": len(physical_blocks),
        "visible_blocks_before_finalize": visible_before,
        "visible_blocks_after_finalize": visible_after,
        "cache_entries_before": cache_before,
        "cache_entries_after": _contractkv_shadow_cache_entries(pool),
        "free_blocks_before": free_before,
        "operation_ms": elapsed_ms,
    })
# CONTRACTKV_EPHEMERAL_SHADOW_HELPER_END
'''

RUNNING = '''            # CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_BEGIN
            _contractkv_shadow_chunk = _contractkv_shadow_chunk_tokens(request)
            if (_contractkv_shadow_chunk is not None
                    and _contractkv_shadow_has_foreground_work(self, request)):
                _contractkv_shadow_write({
                    "event": "shadow_yield",
                    "request_id": request.request_id,
                    "foreground_work": True,
                })
                req_index += 1
                continue
            # CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_END
'''


def strip_region(text: str, begin: str, end: str) -> str:
    while begin in text:
        marker_start = text.index(begin)
        start = text.rfind("\n", 0, marker_start) + 1
        finish = text.index(end, start) + len(end)
        if finish < len(text) and text[finish] == "\n":
            finish += 1
        text = text[:start] + text[finish:]
    return text


def clean(text: str) -> str:
    text = strip_region(text, HELPER_BEGIN, HELPER_END)
    text = strip_region(text, RUNNING_BEGIN, RUNNING_END)
    text = strip_region(text, WAITING_BEGIN, WAITING_END)
    text = text.replace(f"        {FINALIZE_CALL}\n        _contractkv_shadow_finalize(self, request)\n", "")
    text = text.replace(
        "                    delay_cache_blocks=(load_kv_async or _contractkv_shadow_enabled(request)),",
        "                    delay_cache_blocks=load_kv_async,",
    )
    text = text.replace(
        "                    delay_cache_blocks=_contractkv_shadow_enabled(request),\n",
        "",
    )
    text = text.replace(
        "                    num_lookahead_tokens=self.num_lookahead_tokens,\n                    delay_cache_blocks=_contractkv_shadow_enabled(request))",
        "                    num_lookahead_tokens=self.num_lookahead_tokens)",
    )
    text = text.replace(
        "                    num_lookahead_tokens=self.num_lookahead_tokens,\n                    )",
        "                    num_lookahead_tokens=self.num_lookahead_tokens)",
    )
    text = text.replace(
        "            if _contractkv_shadow_chunk is not None:\n                num_new_tokens = min(num_new_tokens, _contractkv_shadow_chunk)\n",
        "",
    )
    text = text.replace(
        "                        num_new_tokens = (request.num_tokens_with_spec +",
        "            num_new_tokens = (request.num_tokens_with_spec +",
    )
    return text


def install(text: str) -> str:
    text = clean(text)
    logger_anchor = "logger = init_logger(__name__)\n"
    if logger_anchor not in text:
        raise RuntimeError("logger anchor not found")
    text = text.replace(logger_anchor, logger_anchor + "\n" + HELPER + "\n", 1)

    running_anchor = "            request = self.running[req_index]\n\n"
    if running_anchor not in text:
        raise RuntimeError("running request anchor not found")
    text = text.replace(running_anchor, running_anchor + RUNNING, 1)

    threshold = '''            if (0 < self.scheduler_config.long_prefill_token_threshold <
                    num_new_tokens):
                num_new_tokens = (
                    self.scheduler_config.long_prefill_token_threshold)
'''
    chunk_cap = threshold + '''            if _contractkv_shadow_chunk is not None:
                num_new_tokens = min(num_new_tokens, _contractkv_shadow_chunk)
'''
    if threshold not in text:
        raise RuntimeError("running chunk threshold anchor not found")
    text = text.replace(threshold, chunk_cap, 1)

    waiting_threshold = '''                    if (0 < self.scheduler_config.long_prefill_token_threshold
                            < num_new_tokens):
                        num_new_tokens = (
                            self.scheduler_config.long_prefill_token_threshold)
'''
    waiting_cap = waiting_threshold + '''                    # CONTRACTKV_EPHEMERAL_SHADOW_WAITING_BEGIN
                    _contractkv_waiting_shadow_chunk = _contractkv_shadow_chunk_tokens(request)
                    if _contractkv_waiting_shadow_chunk is not None:
                        num_new_tokens = min(num_new_tokens, _contractkv_waiting_shadow_chunk)
                    # CONTRACTKV_EPHEMERAL_SHADOW_WAITING_END
'''
    if waiting_threshold not in text:
        raise RuntimeError("waiting chunk threshold anchor not found")
    text = text.replace(waiting_threshold, waiting_cap, 1)

    running_alloc = '''                    num_lookahead_tokens=self.num_lookahead_tokens)
'''
    if running_alloc not in text:
        raise RuntimeError("running allocate anchor not found")
    text = text.replace(
        running_alloc,
        '''                    num_lookahead_tokens=self.num_lookahead_tokens,
                    delay_cache_blocks=_contractkv_shadow_enabled(request))
''',
        1,
    )

    waiting_delay = "                    delay_cache_blocks=load_kv_async,\n"
    if waiting_delay not in text:
        raise RuntimeError("waiting delay-cache anchor not found")
    text = text.replace(
        waiting_delay,
        "                    delay_cache_blocks=(load_kv_async or _contractkv_shadow_enabled(request)),\n",
        1,
    )

    free_anchor = "        delay_free_blocks, kv_xfer_params = self._connector_finished(request)\n"
    if free_anchor not in text:
        raise RuntimeError("request finalize anchor not found")
    text = text.replace(
        free_anchor,
        f"        {FINALIZE_CALL}\n        _contractkv_shadow_finalize(self, request)\n" + free_anchor,
        1,
    )
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler", type=Path, required=True)
    parser.add_argument("--action", choices=["install", "remove"], required=True)
    args = parser.parse_args()
    text = args.scheduler.read_text(encoding="utf-8")
    backup = args.scheduler.with_suffix(args.scheduler.suffix + ".contractkv_ephemeral_shadow.bak")
    if args.action == "install":
        if not backup.exists():
            shutil.copy2(args.scheduler, backup)
        updated = install(text)
    else:
        updated = clean(text)
    args.scheduler.write_text(updated, encoding="utf-8")
    print(f"{args.action}: {args.scheduler}")


if __name__ == "__main__":
    main()
