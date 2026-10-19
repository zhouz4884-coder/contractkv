#!/usr/bin/env python3
"""Install a guarded physical-prefix residency validator in vLLM V1.

The hook uses the Request block hashes produced by vLLM itself.  It snapshots
resident cached blocks immediately before ``get_computed_blocks`` and compares
that snapshot with the native longest-cache-hit result.  No block is pinned and
serving behavior is unchanged when the probe is disabled.
"""

from __future__ import annotations

import argparse
from pathlib import Path


HELPER_BEGIN = "# CONTRACTKV_RESIDENCY_VALIDATOR_HELPER_BEGIN"
HELPER_END = "# CONTRACTKV_RESIDENCY_VALIDATOR_HELPER_END"
CALL_BEGIN = "# CONTRACTKV_RESIDENCY_VALIDATOR_CALL_BEGIN"
CALL_END = "# CONTRACTKV_RESIDENCY_VALIDATOR_CALL_END"
POST_CALL_BEGIN = "# CONTRACTKV_RESIDENCY_VALIDATOR_POST_CALL_BEGIN"
POST_CALL_END = "# CONTRACTKV_RESIDENCY_VALIDATOR_POST_CALL_END"

HELPER = r'''
# CONTRACTKV_RESIDENCY_VALIDATOR_HELPER_BEGIN
_contractkv_residency_predictions = {}


def _contractkv_residency_write(event):
    import json
    import os
    import time as _time
    if os.environ.get("CONTRACTKV_RESIDENCY_VALIDATOR") != "1":
        return
    path = os.environ.get("CONTRACTKV_RESIDENCY_LOG")
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
        pass


def _contractkv_hash_text(value):
    try:
        return bytes(value).hex()
    except Exception:
        return str(value)


def _contractkv_residency_snapshot(scheduler, request):
    import os
    import time as _time
    if os.environ.get("CONTRACTKV_RESIDENCY_VALIDATOR") != "1":
        return None
    started = _time.perf_counter()
    manager = scheduler.kv_cache_manager
    block_pool = manager.block_pool
    return {
        "request_id": request.request_id,
        "cache_epoch": int(getattr(scheduler, "_contractkv_cache_epoch", 0)),
        "block_size": int(manager.block_size),
        "free_gpu_blocks_before": int(block_pool.get_num_free_blocks()),
        "probe_ms": (_time.perf_counter() - started) * 1000.0,
    }


def _contractkv_residency_validate(scheduler, request, snapshot,
                                   computed_blocks, computed_tokens):
    import time as _time
    if snapshot is None:
        return
    started = _time.perf_counter()
    try:
        block_size = int(snapshot["block_size"])
        predicted_count = int(computed_tokens) // block_size if block_size else 0
        first_hash = (_contractkv_hash_text(request.block_hashes[0])
                      if predicted_count else None)
        last_hash = (_contractkv_hash_text(request.block_hashes[predicted_count - 1])
                     if predicted_count else None)
        event = dict(snapshot)
        event.update({
            "expected_hit_blocks": predicted_count,
            "expected_hit_tokens": int(computed_tokens),
            "expected_first_block_hash": first_hash,
            "expected_last_block_hash": last_hash,
            "expected_hash_count": predicted_count,
            "resident_cached_blocks": predicted_count,
            "prediction_ms": (_time.perf_counter() - started) * 1000.0,
        })
        _contractkv_residency_predictions[request.request_id] = event
    except Exception as exc:
        _contractkv_residency_write({
            "event": "prefix_residency_validation_error",
            "request_id": getattr(request, "request_id", ""),
            "error": repr(exc),
        })


def _contractkv_residency_finalize(scheduler, scheduler_output):
    import time as _time
    if not _contractkv_residency_predictions:
        return
    scheduled = getattr(scheduler_output, "num_scheduled_tokens", {}) or {}
    for request_id in scheduled:
        prediction = _contractkv_residency_predictions.pop(request_id, None)
        if prediction is None:
            continue
        started = _time.perf_counter()
        try:
            request = scheduler.requests.get(request_id)
            actual_tokens = int(getattr(request, "num_cached_tokens", 0) or 0)
            block_size = int(prediction["block_size"])
            actual_hit_blocks = actual_tokens // block_size if block_size else 0
            difference = abs(int(prediction["expected_hit_blocks"]) - actual_hit_blocks)
            misprediction = difference > 1
            if misprediction:
                scheduler._contractkv_cache_epoch = int(
                    getattr(scheduler, "_contractkv_cache_epoch", 0)) + 1
            block_pool = scheduler.kv_cache_manager.block_pool
            prediction.update({
                "event": "prefix_residency_validation",
                "actual_hit_blocks": actual_hit_blocks,
                "actual_hit_tokens": actual_tokens,
                "mispredicted_block_count": difference,
                "residency_misprediction": misprediction,
                "cache_epoch_after": int(getattr(scheduler, "_contractkv_cache_epoch", 0)),
                "free_gpu_blocks_after": int(block_pool.get_num_free_blocks()),
                "validation_ms": (_time.perf_counter() - started) * 1000.0,
            })
            _contractkv_residency_write(prediction)
        except Exception as exc:
            _contractkv_residency_write({
                "event": "prefix_residency_validation_error",
                "request_id": request_id,
                "error": repr(exc),
            })
# CONTRACTKV_RESIDENCY_VALIDATOR_HELPER_END
'''

OLD_CALL = '''                    new_computed_blocks, num_new_local_computed_tokens = \\
                        self.kv_cache_manager.get_computed_blocks(
                            request)
'''
NEW_CALL = '''                    # CONTRACTKV_RESIDENCY_VALIDATOR_CALL_BEGIN
                    _contractkv_residency = _contractkv_residency_snapshot(
                        self, request)
                    new_computed_blocks, num_new_local_computed_tokens = \\
                        self.kv_cache_manager.get_computed_blocks(
                            request)
                    _contractkv_residency_validate(
                        self, request, _contractkv_residency,
                        new_computed_blocks, num_new_local_computed_tokens)
                    # CONTRACTKV_RESIDENCY_VALIDATOR_CALL_END
'''

POST_CALL = '''        # CONTRACTKV_RESIDENCY_VALIDATOR_POST_CALL_BEGIN
        _contractkv_residency_finalize(self, scheduler_output)
        # CONTRACTKV_RESIDENCY_VALIDATOR_POST_CALL_END
'''


def _remove_region(text: str, begin: str, end: str) -> str:
    start = text.index(begin)
    finish = text.index(end, start) + len(end)
    return text[:start] + text[finish:]


def install(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if HELPER_BEGIN in text:
        return "already_installed"
    post_needle = "        self._update_after_schedule(scheduler_output)\n"
    if "class Scheduler" not in text or OLD_CALL not in text or post_needle not in text:
        raise RuntimeError("vLLM 0.10.2 scheduler anchors were not found")
    text = text.replace("class Scheduler", HELPER + "\n\nclass Scheduler", 1)
    text = text.replace(OLD_CALL, NEW_CALL, 1)
    text = text.replace(post_needle, POST_CALL + post_needle, 1)
    path.write_text(text, encoding="utf-8")
    return "installed"


def uninstall(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if HELPER_BEGIN not in text:
        return "not_installed"
    text = _remove_region(text, HELPER_BEGIN, HELPER_END)
    marker_start = text.index(CALL_BEGIN)
    start = text.rfind("\n", 0, marker_start) + 1
    finish = text.index(CALL_END, marker_start) + len(CALL_END)
    text = text[:start] + OLD_CALL.rstrip("\n") + text[finish:]
    marker_start = text.index(POST_CALL_BEGIN)
    start = text.rfind("\n", 0, marker_start) + 1
    finish = text.index(POST_CALL_END, marker_start) + len(POST_CALL_END)
    text = text[:start] + text[finish:]
    path.write_text(text, encoding="utf-8")
    return "uninstalled"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduler", type=Path, required=True)
    parser.add_argument("--action", choices=("install", "uninstall"), default="install")
    args = parser.parse_args()
    print(install(args.scheduler) if args.action == "install" else uninstall(args.scheduler))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
