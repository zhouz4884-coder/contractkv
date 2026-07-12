#!/usr/bin/env python3
"""Install opt-in PSTP and burst-aware shadow admission hooks in vLLM V1."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


HELPER_BEGIN = "# CONTRACTKV_EPHEMERAL_SHADOW_HELPER_BEGIN"
HELPER_END = "# CONTRACTKV_EPHEMERAL_SHADOW_HELPER_END"
RUNNING_BEGIN = "# CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_BEGIN"
RUNNING_END = "# CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_END"
WAITING_CAP_BEGIN = "# CONTRACTKV_EPHEMERAL_SHADOW_WAITING_BEGIN"
WAITING_CAP_END = "# CONTRACTKV_EPHEMERAL_SHADOW_WAITING_END"
WAITING_GATE_BEGIN = "# CONTRACTKV_QUIESCENCE_WAITING_BEGIN"
WAITING_GATE_END = "# CONTRACTKV_QUIESCENCE_WAITING_END"
BEGIN_ROUND_CALL = "# CONTRACTKV_QUIESCENCE_BEGIN_ROUND_CALL"
END_ROUND_CALL = "# CONTRACTKV_QUIESCENCE_END_ROUND_CALL"
ADD_REQUEST_CALL = "# CONTRACTKV_PSTP_ADD_REQUEST_CALL"
ADMISSION_CALL = "# CONTRACTKV_QUIESCENCE_ADMISSION_CALL"
FINALIZE_CALL = "# CONTRACTKV_EPHEMERAL_SHADOW_FINALIZE_CALL"
COMPLETION_CALL = "# CONTRACTKV_QUIESCENCE_COMPLETION_CALL"


HELPER = r'''# CONTRACTKV_EPHEMERAL_SHADOW_HELPER_BEGIN
def _contractkv_write(event):
    import os
    import time as _time
    mode = os.environ.get("CONTRACTKV_TRACE_MODE", "SYNC_JSONL").upper()
    if mode in {"OFF", "COUNTERS", "RING"}:
        return
    import json
    path = os.environ.get("CONTRACTKV_PHASE16R_EVENT_LOG") or os.environ.get("CONTRACTKV_EPHEMERAL_SHADOW_LOG")
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


def _contractkv_attach_pstp(request):
    if getattr(request, "contractkv_pstp", None) is not None:
        return getattr(request, "contractkv_pstp")
    try:
        from scripts.contractkv_pstp import lookup_pstp_spec
        spec = lookup_pstp_spec(str(request.request_id))
        if spec is not None:
            request.contractkv_pstp = spec
            _contractkv_write({
                "event": "pstp_attached",
                "request_id": request.request_id,
                "txn_id": spec.txn_id,
                "verify_decision": spec.verify_decision.value,
                "stable_prefix_end_token": spec.stable_prefix_end_token,
                "shadow_work": spec.shadow_work,
            })
        return spec
    except Exception as exc:
        _contractkv_write({"event": "pstp_attach_error", "request_id": getattr(request, "request_id", ""), "error": repr(exc)})
        return None


def _contractkv_pstp_enabled(request):
    return _contractkv_attach_pstp(request) is not None


def _contractkv_shadow_enabled(request):
    spec = _contractkv_attach_pstp(request)
    return bool(spec is not None and getattr(spec, "shadow_work", True))


def _contractkv_is_foreground(request):
    return not _contractkv_shadow_enabled(request)


def _contractkv_init_state(scheduler):
    import os
    import time as _time
    if getattr(scheduler, "_contractkv_state_ready", False):
        return
    now = _time.monotonic_ns()
    scheduler._contractkv_state_ready = True
    scheduler.last_fg_arrival_ns = now
    scheduler.last_fg_admission_ns = now
    scheduler.last_fg_schedule_ns = now
    scheduler.last_fg_completion_ns = now
    scheduler.shadow_backoff_until_ns = 0
    scheduler.shadow_collision_count = 0
    scheduler.previous_round_shadow_tokens = 0
    scheduler.previous_round_shadow_start_ns = 0
    scheduler._contractkv_round_id = 0
    scheduler._contractkv_round_shadow_reserved = 0
    scheduler.idle_grace_ms = float(os.environ.get("CONTRACTKV_IDLE_GRACE_MS", "0"))
    scheduler.base_backoff_ms = float(os.environ.get("CONTRACTKV_BASE_BACKOFF_MS", "1"))
    scheduler.max_backoff_ms = float(os.environ.get("CONTRACTKV_MAX_BACKOFF_MS", "8"))
    scheduler.shadow_block_watermark = int(os.environ.get("CONTRACTKV_SHADOW_BLOCK_WATERMARK", "0"))


def _contractkv_last_foreground_activity_ns(scheduler):
    _contractkv_init_state(scheduler)
    return max(
        scheduler.last_fg_arrival_ns,
        scheduler.last_fg_admission_ns,
        scheduler.last_fg_schedule_ns,
        scheduler.last_fg_completion_ns,
    )


def _contractkv_has_foreground_waiting(scheduler):
    return any(_contractkv_is_foreground(req) for req in scheduler.waiting)


def _contractkv_has_foreground_running(scheduler, current_request=None):
    return any(req is not current_request and _contractkv_is_foreground(req) for req in scheduler.running)


def _contractkv_record_arrival(scheduler, request):
    import time as _time
    _contractkv_init_state(scheduler)
    if _contractkv_is_foreground(request):
        scheduler.last_fg_arrival_ns = _time.monotonic_ns()


def _contractkv_record_admission(scheduler, request):
    import time as _time
    _contractkv_init_state(scheduler)
    if _contractkv_is_foreground(request):
        scheduler.last_fg_admission_ns = _time.monotonic_ns()


def _contractkv_record_completion(scheduler, request):
    import time as _time
    _contractkv_init_state(scheduler)
    if _contractkv_is_foreground(request):
        scheduler.last_fg_completion_ns = _time.monotonic_ns()


def _contractkv_begin_round(scheduler):
    import time as _time
    _contractkv_init_state(scheduler)
    scheduler._contractkv_round_id += 1
    scheduler._contractkv_round_shadow_reserved = 0
    now = _time.monotonic_ns()
    foreground = _contractkv_has_foreground_waiting(scheduler) or _contractkv_has_foreground_running(scheduler)
    collision = scheduler.previous_round_shadow_tokens > 0 and foreground
    if collision:
        scheduler.shadow_collision_count += 1
        backoff_ms = min(
            scheduler.max_backoff_ms,
            scheduler.base_backoff_ms * (2 ** (scheduler.shadow_collision_count - 1)),
        )
        scheduler.shadow_backoff_until_ns = now + int(backoff_ms * 1e6)
        wait_ms = max(0.0, (now - scheduler.previous_round_shadow_start_ns) / 1e6)
        _contractkv_write({
            "event": "shadow_collision",
            "collision_count": scheduler.shadow_collision_count,
            "backoff_ms": backoff_ms,
            "previous_round_shadow_tokens": scheduler.previous_round_shadow_tokens,
            "foreground_wait_ms": wait_ms,
        })
    else:
        scheduler.shadow_collision_count = max(0, scheduler.shadow_collision_count - 1)


def _contractkv_should_admit_shadow(scheduler, request):
    import os
    import time as _time
    from scripts.contractkv_quiescence import decide_shadow_admission
    _contractkv_init_state(scheduler)
    now = _time.monotonic_ns()
    free_blocks = scheduler.kv_cache_manager.block_pool.get_num_free_blocks()
    idle_age_ms = (now - _contractkv_last_foreground_activity_ns(scheduler)) / 1e6
    cached = getattr(request, "_contractkv_shadow_admission", None)
    if cached is not None and cached.get("round_id") == scheduler._contractkv_round_id:
        return cached
    requested_tokens = _contractkv_shadow_chunk_tokens(request) or 0
    global_budget = max(1, int(os.environ.get("CONTRACTKV_SHADOW_ROUND_TOKENS", "32")))
    available_tokens = max(0, global_budget - scheduler._contractkv_round_shadow_reserved)
    report = decide_shadow_admission(
        foreground_waiting=_contractkv_has_foreground_waiting(scheduler),
        foreground_running=_contractkv_has_foreground_running(scheduler, request),
        in_collision_backoff=now < scheduler.shadow_backoff_until_ns,
        idle_age_ms=idle_age_ms,
        idle_grace_ms=scheduler.idle_grace_ms,
        free_blocks=free_blocks,
        block_watermark=scheduler.shadow_block_watermark,
        collision_count=scheduler.shadow_collision_count,
        current_backoff_ms=(scheduler.shadow_backoff_until_ns - now) / 1e6,
        chunk_tokens=min(requested_tokens, available_tokens),
        quiescence_enabled=os.environ.get("CONTRACTKV_QUIESCENCE", "1") == "1",
    ).as_dict()
    if report["admitted"] and available_tokens <= 0:
        report["admitted"] = False
        report["reason"] = "shadow_round_budget"
    if report["admitted"]:
        scheduler._contractkv_round_shadow_reserved += int(report["chunk_tokens"])
    report.update({
        "event": "shadow_admission",
        "request_id": request.request_id,
        "round_id": scheduler._contractkv_round_id,
        "global_shadow_budget_tokens": global_budget,
        "round_shadow_reserved_tokens": scheduler._contractkv_round_shadow_reserved,
    })
    request._contractkv_shadow_admission = report
    _contractkv_write(report)
    return report


def _contractkv_shadow_chunk_tokens(request):
    import os
    if not _contractkv_shadow_enabled(request):
        return None
    try:
        return max(1, int(os.environ.get("CONTRACTKV_SHADOW_CHUNK_TOKENS", "32")))
    except ValueError:
        return 32


def _contractkv_shadow_granted_tokens(request):
    if not _contractkv_shadow_enabled(request):
        return None
    report = getattr(request, "_contractkv_shadow_admission", None) or {}
    return int(report.get("chunk_tokens", 0))


def _contractkv_end_round(scheduler, scheduler_output):
    import time as _time
    _contractkv_init_state(scheduler)
    shadow_tokens = 0
    foreground_tokens = 0
    shadow_request_tokens = {}
    for request_id, tokens in scheduler_output.num_scheduled_tokens.items():
        request = scheduler.requests.get(request_id)
        if request is not None and _contractkv_shadow_enabled(request):
            shadow_tokens += int(tokens)
            shadow_request_tokens[str(request_id)] = int(tokens)
        else:
            foreground_tokens += int(tokens)
    now = _time.monotonic_ns()
    scheduler.previous_round_shadow_tokens = shadow_tokens
    if shadow_tokens > 0:
        scheduler.previous_round_shadow_start_ns = now
        _contractkv_write({
            "event": "shadow_round",
            "shadow_tokens": shadow_tokens,
            "foreground_tokens": foreground_tokens,
            "shadow_request_tokens": shadow_request_tokens,
            "max_shadow_request_tokens": max(shadow_request_tokens.values(), default=0),
            "global_shadow_budget_tokens": int(__import__("os").environ.get("CONTRACTKV_SHADOW_ROUND_TOKENS", "32")),
        })
    if foreground_tokens > 0:
        scheduler.last_fg_schedule_ns = now


def _contractkv_cache_entries(pool):
    return sum(len(blocks) for blocks in pool.cached_block_hash_to_block.values())


def _contractkv_pstp_finalize(scheduler, request):
    import os
    import time as _time
    spec = _contractkv_attach_pstp(request)
    if spec is None:
        return
    if getattr(request, "_contractkv_finalized", False):
        _contractkv_write({"event": "pstp_finalize_duplicate", "request_id": request.request_id, "txn_id": spec.txn_id})
        return
    request._contractkv_finalized = True
    from scripts.contractkv_pstp import VerifyDecision, aligned_commit_tokens

    pool = scheduler.kv_cache_manager.block_pool
    blocks = scheduler.kv_cache_manager.get_blocks(request.request_id)
    physical_blocks = [block for group in blocks.blocks for block in group]
    cache_before = _contractkv_cache_entries(pool)
    visible_before = sum(block.block_hash is not None for block in physical_blocks)
    num_computed_tokens = int(getattr(request, "num_computed_tokens", 0) or 0)
    commit_tokens = aligned_commit_tokens(spec.stable_prefix_end_token, num_computed_tokens, scheduler.block_size)
    decision = spec.verify_decision
    if spec.tokenization_glue_loss >= scheduler.block_size:
        decision = VerifyDecision.INCOMPLETE
    started = _time.perf_counter()
    if decision is VerifyDecision.PASS and commit_tokens > 0:
        scheduler.kv_cache_manager.cache_blocks(request, commit_tokens)
        action = "commit"
    else:
        commit_tokens = 0
        action = "abort"
    elapsed_ms = (_time.perf_counter() - started) * 1000.0
    visible_after = sum(block.block_hash is not None for block in physical_blocks)
    _contractkv_write({
        "event": "pstp_finalize",
        "request_id": request.request_id,
        "txn_id": spec.txn_id,
        "action": action,
        "verify_decision": decision.value,
        "failure_reason": spec.failure_reason,
        "expected_stable_tokens": spec.expected_stable_tokens,
        "stable_prefix_end_token": spec.stable_prefix_end_token,
        "tokenization_glue_loss": spec.tokenization_glue_loss,
        "glue_status": spec.glue_status,
        "num_computed_tokens": num_computed_tokens,
        "block_size": scheduler.block_size,
        "commit_tokens": commit_tokens,
        "committed_full_blocks": commit_tokens // scheduler.block_size,
        "discarded_partial_tokens": max(0, spec.stable_prefix_end_token - commit_tokens),
        "physical_blocks": len(physical_blocks),
        "visible_blocks_before_finalize": visible_before,
        "visible_blocks_after_finalize": visible_after,
        "cache_entries_before": cache_before,
        "cache_entries_after": _contractkv_cache_entries(pool),
        "operation_ms": elapsed_ms,
    })
    if os.environ.get("CONTRACTKV_PSTP_DOUBLE_FINALIZE") == "1":
        _contractkv_pstp_finalize(scheduler, request)
# CONTRACTKV_EPHEMERAL_SHADOW_HELPER_END
'''


RUNNING = '''            # CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_BEGIN
            _contractkv_shadow_chunk = _contractkv_shadow_chunk_tokens(request)
            if _contractkv_shadow_chunk is not None:
                _contractkv_gate = _contractkv_should_admit_shadow(self, request)
                if not _contractkv_gate["admitted"]:
                    req_index += 1
                    continue
            # CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_END
'''

WAITING_GATE = '''                # CONTRACTKV_QUIESCENCE_WAITING_BEGIN
                if _contractkv_shadow_enabled(request):
                    _contractkv_waiting_gate = _contractkv_should_admit_shadow(self, request)
                    if not _contractkv_waiting_gate["admitted"]:
                        self.waiting.pop_request()
                        skipped_waiting_requests.prepend_request(request)
                        continue
                # CONTRACTKV_QUIESCENCE_WAITING_END
'''


def strip_region(text: str, begin: str, end: str) -> str:
    while begin in text:
        marker_start = text.index(begin)
        start = text.rfind("\n", 0, marker_start) + 1
        finish = text.index(end, marker_start) + len(end)
        if finish < len(text) and text[finish] == "\n":
            finish += 1
        text = text[:start] + text[finish:]
    return text


def clean(text: str) -> str:
    for begin, end in [
        (HELPER_BEGIN, HELPER_END),
        (RUNNING_BEGIN, RUNNING_END),
        (WAITING_CAP_BEGIN, WAITING_CAP_END),
        (WAITING_GATE_BEGIN, WAITING_GATE_END),
    ]:
        text = strip_region(text, begin, end)
    call_lines = [
        (BEGIN_ROUND_CALL, "_contractkv_begin_round(self)"),
        (END_ROUND_CALL, "_contractkv_end_round(self, scheduler_output)"),
        (ADD_REQUEST_CALL, "_contractkv_attach_pstp(request)\n        _contractkv_record_arrival(self, request)"),
        (ADMISSION_CALL, "_contractkv_record_admission(self, request)"),
        (FINALIZE_CALL, "_contractkv_pstp_finalize(self, request)"),
        (COMPLETION_CALL, "_contractkv_record_completion(self, request)"),
    ]
    for marker, call in call_lines:
        text = text.replace(f"        {marker}\n        {call}\n", "")
        text = text.replace(f"                {marker}\n                {call}\n", "")
    # Phase 16 used the same marker with the legacy request-id-driven finalizer.
    text = text.replace(
        f"        {FINALIZE_CALL}\n        _contractkv_shadow_finalize(self, request)\n",
        "",
    )
    text = text.replace(
        "                    delay_cache_blocks=(load_kv_async or _contractkv_pstp_enabled(request)),",
        "                    delay_cache_blocks=load_kv_async,",
    )
    text = text.replace(
        "                    delay_cache_blocks=(load_kv_async or _contractkv_shadow_enabled(request)),",
        "                    delay_cache_blocks=load_kv_async,",
    )
    for suffix in [
        "                    delay_cache_blocks=_contractkv_pstp_enabled(request))",
        "                    delay_cache_blocks=_contractkv_shadow_enabled(request))",
    ]:
        text = text.replace(
            "                    num_lookahead_tokens=self.num_lookahead_tokens,\n" + suffix,
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

    timestamp_anchor = "        scheduled_timestamp = time.monotonic()\n"
    if timestamp_anchor not in text:
        raise RuntimeError("schedule timestamp anchor not found")
    text = text.replace(timestamp_anchor, timestamp_anchor + f"        {BEGIN_ROUND_CALL}\n        _contractkv_begin_round(self)\n", 1)

    running_anchor = "            request = self.running[req_index]\n\n"
    if running_anchor not in text:
        raise RuntimeError("running request anchor not found")
    text = text.replace(running_anchor, running_anchor + RUNNING, 1)

    running_threshold = '''            if (0 < self.scheduler_config.long_prefill_token_threshold <
                    num_new_tokens):
                num_new_tokens = (
                    self.scheduler_config.long_prefill_token_threshold)
'''
    running_cap = running_threshold + '''            if _contractkv_shadow_chunk is not None:
                num_new_tokens = min(num_new_tokens, _contractkv_shadow_granted_tokens(request))
'''
    if running_threshold not in text:
        raise RuntimeError("running chunk threshold anchor not found")
    text = text.replace(running_threshold, running_cap, 1)

    waiting_peek = "                request = self.waiting.peek_request()\n\n"
    if waiting_peek not in text:
        raise RuntimeError("waiting peek anchor not found")
    text = text.replace(waiting_peek, waiting_peek + WAITING_GATE, 1)

    waiting_threshold = '''                    if (0 < self.scheduler_config.long_prefill_token_threshold
                            < num_new_tokens):
                        num_new_tokens = (
                            self.scheduler_config.long_prefill_token_threshold)
'''
    waiting_cap = waiting_threshold + '''                    # CONTRACTKV_EPHEMERAL_SHADOW_WAITING_BEGIN
                    _contractkv_waiting_shadow_chunk = _contractkv_shadow_granted_tokens(request)
                    if _contractkv_waiting_shadow_chunk is not None:
                        num_new_tokens = min(num_new_tokens, _contractkv_waiting_shadow_chunk)
                    # CONTRACTKV_EPHEMERAL_SHADOW_WAITING_END
'''
    if waiting_threshold not in text:
        raise RuntimeError("waiting chunk threshold anchor not found")
    text = text.replace(waiting_threshold, waiting_cap, 1)

    running_alloc = "                    num_lookahead_tokens=self.num_lookahead_tokens)\n"
    if running_alloc not in text:
        raise RuntimeError("running allocate anchor not found")
    text = text.replace(
        running_alloc,
        "                    num_lookahead_tokens=self.num_lookahead_tokens,\n                    delay_cache_blocks=_contractkv_pstp_enabled(request))\n",
        1,
    )

    waiting_delay = "                    delay_cache_blocks=load_kv_async,\n"
    if waiting_delay not in text:
        raise RuntimeError("waiting delay-cache anchor not found")
    text = text.replace(
        waiting_delay,
        "                    delay_cache_blocks=(load_kv_async or _contractkv_pstp_enabled(request)),\n",
        1,
    )

    append_running = "                self.running.append(request)\n"
    if append_running not in text:
        raise RuntimeError("admission anchor not found")
    text = text.replace(
        append_running,
        append_running + f"                {ADMISSION_CALL}\n                _contractkv_record_admission(self, request)\n",
        1,
    )

    end_round_anchor = "        self._update_after_schedule(scheduler_output)\n"
    if end_round_anchor not in text:
        raise RuntimeError("end round anchor not found")
    text = text.replace(
        end_round_anchor,
        f"        {END_ROUND_CALL}\n        _contractkv_end_round(self, scheduler_output)\n" + end_round_anchor,
        1,
    )

    add_anchor = "    def add_request(self, request: Request) -> None:\n        self.waiting.add_request(request)\n"
    if add_anchor not in text:
        raise RuntimeError("add request anchor not found")
    text = text.replace(
        add_anchor,
        "    def add_request(self, request: Request) -> None:\n"
        f"        {ADD_REQUEST_CALL}\n        _contractkv_attach_pstp(request)\n        _contractkv_record_arrival(self, request)\n"
        "        self.waiting.add_request(request)\n",
        1,
    )

    free_anchor = "        delay_free_blocks, kv_xfer_params = self._connector_finished(request)\n"
    if free_anchor not in text:
        raise RuntimeError("request finalize anchor not found")
    text = text.replace(
        free_anchor,
        f"        {COMPLETION_CALL}\n        _contractkv_record_completion(self, request)\n"
        f"        {FINALIZE_CALL}\n        _contractkv_pstp_finalize(self, request)\n" + free_anchor,
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
