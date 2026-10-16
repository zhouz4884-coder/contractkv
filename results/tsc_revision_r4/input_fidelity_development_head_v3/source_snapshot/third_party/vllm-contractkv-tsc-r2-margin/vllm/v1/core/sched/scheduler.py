# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

from __future__ import annotations

import itertools
import hashlib
import os
from scripts.tsc_revision_r2_margin_policy import minimum_margin_gate
from scripts.tsc_revision_r2_execution_trace import emit_trace
import time
from collections import defaultdict
from collections.abc import Iterable
from typing import Any, Optional, Union

from vllm.config import VllmConfig
from vllm.distributed.kv_events import EventPublisherFactory, KVEventBatch
from vllm.distributed.kv_transfer.kv_connector.factory import (
    KVConnectorFactory)
from vllm.distributed.kv_transfer.kv_connector.v1 import (KVConnectorBase_V1,
                                                          KVConnectorRole)
from vllm.logger import init_logger
from vllm.multimodal import MULTIMODAL_REGISTRY, MultiModalRegistry
from vllm.v1.core.encoder_cache_manager import (EncoderCacheManager,
                                                compute_encoder_budget)
from vllm.v1.core.kv_cache_manager import KVCacheBlocks, KVCacheManager
from vllm.v1.core.sched.interface import SchedulerInterface
from vllm.v1.core.sched.output import (CachedRequestData, NewRequestData,
                                       SchedulerOutput)
from vllm.v1.core.sched.request_queue import (SchedulingPolicy,
                                              create_request_queue)
from vllm.v1.core.sched.utils import check_stop, remove_all
from vllm.v1.engine import (ContractKVCompactResult, EngineCoreEventType,
                            EngineCoreOutput, EngineCoreOutputs)
from vllm.v1.kv_cache_interface import KVCacheConfig
from vllm.v1.metrics.stats import SchedulerStats
from vllm.v1.outputs import DraftTokenIds, KVConnectorOutput, ModelRunnerOutput
from vllm.v1.request import Request, RequestStatus
from vllm.v1.spec_decode.metrics import SpecDecodingStats
from vllm.v1.structured_output import StructuredOutputManager

logger = init_logger(__name__)

# CONTRACTKV_EPHEMERAL_SHADOW_HELPER_BEGIN
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
    native_spec = getattr(request, "contractkv_verify_spec", None)
    if native_spec is not None:
        request.contractkv_pstp = native_spec
        return native_spec
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
    from scripts.contractkv_shadow_parking import ShadowParking
    scheduler.contractkv_shadow_parking = ShadowParking()


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


def _contractkv_park_and_wake(scheduler):
    import os
    if os.environ.get("CONTRACTKV_PARKING", "1") != "1":
        return
    import time as _time
    _contractkv_init_state(scheduler)
    now = _time.monotonic_ns()
    foreground = _contractkv_has_foreground_waiting(scheduler) or _contractkv_has_foreground_running(scheduler)
    if foreground:
        # A RUNNING request cannot be moved into the waiting queue without the
        # scheduler's native preemption transition.  The running-loop admission
        # gate already pauses shadow work in place, preserving status and KV
        # ownership.  Parking is therefore restricted to not-yet-admitted
        # waiting requests below.
        return
    deadline = max(_contractkv_last_foreground_activity_ns(scheduler) + int(scheduler.idle_grace_ms * 1e6), scheduler.shadow_backoff_until_ns)
    for parked in scheduler.contractkv_shadow_parking.wake(now if now >= deadline else -1, max_wake=1):
        scheduler.waiting.add_request(parked.request)


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
    if getattr(request, "contractkv_verify_spec", None) is not None:
        # Source-level compact verification owns its finalization path.
        return
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


class Scheduler(SchedulerInterface):

    def __init__(
        self,
        vllm_config: VllmConfig,
        kv_cache_config: KVCacheConfig,
        structured_output_manager: StructuredOutputManager,
        mm_registry: MultiModalRegistry = MULTIMODAL_REGISTRY,
        include_finished_set: bool = False,
        log_stats: bool = False,
    ) -> None:
        self.vllm_config = vllm_config
        self.scheduler_config = vllm_config.scheduler_config
        self.cache_config = vllm_config.cache_config
        self.lora_config = vllm_config.lora_config
        self.kv_cache_config = kv_cache_config
        self.kv_events_config = vllm_config.kv_events_config
        self.parallel_config = vllm_config.parallel_config
        self.log_stats = log_stats
        self.structured_output_manager = structured_output_manager
        self.is_encoder_decoder = vllm_config.model_config.is_encoder_decoder

        # include_finished_set controls whether a separate set of finished
        # request ids should be included in the EngineCoreOutputs returned
        # by update_from_outputs(). This is currently used in the multi-engine
        # case to track request lifetimes efficiently.
        self.finished_req_ids_dict: Optional[dict[int, set[str]]] = (
            defaultdict(set) if include_finished_set else None)

        # Scheduling constraints.
        self.max_num_running_reqs = self.scheduler_config.max_num_seqs
        self.max_num_scheduled_tokens = \
            self.scheduler_config.max_num_batched_tokens
        self.max_model_len = self.scheduler_config.max_model_len
        self.enable_kv_cache_events = (
            self.kv_events_config is not None
            and self.kv_events_config.enable_kv_cache_events)

        # Create KVConnector for the Scheduler. Note that each Worker
        # will have a corresponding KVConnector with Role=WORKER.
        # KV Connector pushes/pull of remote KVs for P/D and offloading.
        self.connector = None
        if self.vllm_config.kv_transfer_config is not None:
            assert len(self.kv_cache_config.kv_cache_groups) == 1, (
                "Multiple KV cache groups are not currently supported "
                "with KV connectors")
            assert not self.is_encoder_decoder, (
                "Encoder-decoder models are not currently supported "
                "with KV connectors")
            self.connector = KVConnectorFactory.create_connector(
                config=self.vllm_config, role=KVConnectorRole.SCHEDULER)

        self.kv_event_publisher = EventPublisherFactory.create(
            self.kv_events_config,
            self.parallel_config.data_parallel_rank,
        )

        num_gpu_blocks = self.cache_config.num_gpu_blocks
        assert num_gpu_blocks is not None and num_gpu_blocks > 0

        self.block_size = self.cache_config.block_size

        self.dcp_world_size = \
            vllm_config.parallel_config.decode_context_parallel_size
        # Note(hc): The scheduler’s block_size must be multiplied
        # by dcp_world_size, since block hashes are computed on the
        # original full token sequence at a granularity of
        # original_block_size × dcp_world_size.
        if self.dcp_world_size > 1:
            self.block_size *= self.dcp_world_size

        # req_id -> Request
        self.requests: dict[str, Request] = {}
        # Scheduling policy
        if self.scheduler_config.policy == "priority":
            self.policy = SchedulingPolicy.PRIORITY
        elif self.scheduler_config.policy == "fcfs":
            self.policy = SchedulingPolicy.FCFS
        else:
            raise ValueError(
                f"Unknown scheduling policy: {self.scheduler_config.policy}")
        # Priority queues for requests.
        self.waiting = create_request_queue(self.policy)
        self.running: list[Request] = []

        # The request IDs that are finished in between the previous and the
        # current steps. This is used to notify the workers about the finished
        # requests so that they can free the cached states for those requests.
        # This is flushed at the end of each scheduling step.
        self.finished_req_ids: set[str] = set()

        # KV Connector: requests in process of async KV loading or recving
        self.finished_recving_kv_req_ids: set[str] = set()

        # Encoder-related.
        # Calculate encoder cache size if applicable
        # NOTE: For now we use the same budget for both compute and space.
        # This can be changed when we make encoder cache for embedding caching
        # across requests.
        encoder_compute_budget, encoder_cache_size = compute_encoder_budget(
            model_config=vllm_config.model_config,
            scheduler_config=vllm_config.scheduler_config,
            mm_registry=mm_registry,
        )

        # NOTE(woosuk): Here, "encoder" includes the vision encoder (and
        # projector if needed) for MM models as well as encoder-decoder
        # transformers.
        self.max_num_encoder_input_tokens = encoder_compute_budget
        # NOTE: For the models without encoder (e.g., text-only models),
        # the encoder cache will not be initialized because cache size is 0
        # for these models.
        self.encoder_cache_manager = EncoderCacheManager(
            cache_size=encoder_cache_size)

        speculative_config = vllm_config.speculative_config
        self.use_eagle = False
        self.num_spec_tokens = self.num_lookahead_tokens = 0
        if speculative_config:
            self.num_spec_tokens = speculative_config.num_speculative_tokens
            if speculative_config.use_eagle():
                self.use_eagle = True
                self.num_lookahead_tokens = self.num_spec_tokens

        # Create the KV cache manager.
        self.kv_cache_manager = KVCacheManager(
            kv_cache_config=kv_cache_config,
            max_model_len=self.max_model_len,
            enable_caching=self.cache_config.enable_prefix_caching,
            use_eagle=self.use_eagle,
            log_stats=self.log_stats,
            enable_kv_cache_events=self.enable_kv_cache_events,
            dcp_world_size=self.dcp_world_size,
        )
        self.use_pp = self.parallel_config.pipeline_parallel_size > 1

    def schedule(self) -> SchedulerOutput:
        # NOTE(woosuk) on the scheduling algorithm:
        # There's no "decoding phase" nor "prefill phase" in the scheduler.
        # Each request just has the num_computed_tokens and
        # num_tokens_with_spec. num_tokens_with_spec =
        # len(prompt_token_ids) + len(output_token_ids) + len(spec_token_ids).
        # At each step, the scheduler tries to assign tokens to the requests
        # so that each request's num_computed_tokens can catch up its
        # num_tokens_with_spec. This is general enough to cover
        # chunked prefills, prefix caching, speculative decoding,
        # and the "jump decoding" optimization in the future.

        scheduled_new_reqs: list[Request] = []
        scheduled_resumed_reqs: list[Request] = []
        scheduled_running_reqs: list[Request] = []
        preempted_reqs: list[Request] = []

        req_to_new_blocks: dict[str, KVCacheBlocks] = {}
        num_scheduled_tokens: dict[str, int] = {}
        token_budget = self.max_num_scheduled_tokens
        # Encoder-related.
        scheduled_encoder_inputs: dict[str, list[int]] = {}
        encoder_compute_budget = self.max_num_encoder_input_tokens
        # Spec decode-related.
        scheduled_spec_decode_tokens: dict[str, list[int]] = {}

        # For logging.
        scheduled_timestamp = time.monotonic()
        # CONTRACTKV_QUIESCENCE_BEGIN_ROUND_CALL
        _contractkv_begin_round(self)
        # CONTRACTKV_QUIESCENCE_PARKING_CALL
        _contractkv_park_and_wake(self)

        # First, schedule the RUNNING requests.
        req_index = 0
        while req_index < len(self.running) and token_budget > 0:
            request = self.running[req_index]

            # CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_BEGIN
            _contractkv_shadow_chunk = _contractkv_shadow_chunk_tokens(request)
            if _contractkv_shadow_chunk is not None:
                _contractkv_gate = _contractkv_should_admit_shadow(self, request)
                if not _contractkv_gate["admitted"]:
                    req_index += 1
                    continue
            # CONTRACTKV_EPHEMERAL_SHADOW_RUNNING_END
            num_new_tokens = (request.num_tokens_with_spec +
                              request.num_output_placeholders -
                              request.num_computed_tokens)
            if (0 < self.scheduler_config.long_prefill_token_threshold <
                    num_new_tokens):
                num_new_tokens = (
                    self.scheduler_config.long_prefill_token_threshold)
            if _contractkv_shadow_chunk is not None:
                num_new_tokens = min(num_new_tokens, _contractkv_shadow_granted_tokens(request))
            num_new_tokens = min(num_new_tokens, token_budget)

            # Make sure the input position does not exceed the max model len.
            # This is necessary when using spec decoding.
            num_new_tokens = min(
                num_new_tokens,
                self.max_model_len - 1 - request.num_computed_tokens)

            # Schedule encoder inputs.
            encoder_inputs_to_schedule = None
            new_encoder_compute_budget = encoder_compute_budget
            if request.has_encoder_inputs:
                (encoder_inputs_to_schedule, num_new_tokens,
                 new_encoder_compute_budget
                 ) = self._try_schedule_encoder_inputs(
                     request, request.num_computed_tokens, num_new_tokens,
                     encoder_compute_budget)

            if num_new_tokens == 0:
                # The request cannot be scheduled because one of the following
                # reasons:
                # 1. No new tokens to schedule. This may happen when
                #    (1) PP>1 and we have already scheduled all prompt tokens
                #    but they are not finished yet.
                #    (2) Async scheduling and the request has reached to either
                #    its max_total_tokens or max_model_len.
                # 2. The encoder budget is exhausted.
                # 3. The encoder cache is exhausted.
                # NOTE(woosuk): Here, by doing `continue` instead of `break`,
                # we do not strictly follow the FCFS scheduling policy and
                # allow the lower-priority requests to be scheduled.
                req_index += 1
                continue

            while True:
                new_blocks = self.kv_cache_manager.allocate_slots(
                    request,
                    num_new_tokens,
                    num_lookahead_tokens=self.num_lookahead_tokens,
                    delay_cache_blocks=_contractkv_pstp_enabled(request))
                if new_blocks is None:
                    # The request cannot be scheduled.
                    # Preempt the lowest-priority request.
                    if self.policy == SchedulingPolicy.PRIORITY:
                        preempted_req = max(
                            self.running,
                            key=lambda r: (r.priority, r.arrival_time),
                        )
                        self.running.remove(preempted_req)
                        if preempted_req in scheduled_running_reqs:
                            scheduled_running_reqs.remove(preempted_req)
                    else:
                        preempted_req = self.running.pop()

                    self.kv_cache_manager.free(preempted_req)
                    self.encoder_cache_manager.free(preempted_req)
                    preempted_req.status = RequestStatus.PREEMPTED
                    preempted_req.num_computed_tokens = 0
                    if self.log_stats:
                        preempted_req.record_event(
                            EngineCoreEventType.PREEMPTED, scheduled_timestamp)

                    self.waiting.prepend_request(preempted_req)
                    preempted_reqs.append(preempted_req)
                    if preempted_req == request:
                        # No more request to preempt.
                        can_schedule = False
                        break
                else:
                    # The request can be scheduled.
                    can_schedule = True
                    break
            if not can_schedule:
                break
            assert new_blocks is not None

            # Schedule the request.
            scheduled_running_reqs.append(request)
            req_to_new_blocks[request.request_id] = new_blocks
            num_scheduled_tokens[request.request_id] = num_new_tokens
            token_budget -= num_new_tokens
            req_index += 1

            # Speculative decode related.
            if request.spec_token_ids:
                num_scheduled_spec_tokens = (num_new_tokens +
                                             request.num_computed_tokens -
                                             request.num_tokens)
                if num_scheduled_spec_tokens > 0:
                    # Trim spec_token_ids list to num_scheduled_spec_tokens.
                    del request.spec_token_ids[num_scheduled_spec_tokens:]
                    scheduled_spec_decode_tokens[request.request_id] = (
                        request.spec_token_ids)

            # Encoder-related.
            if encoder_inputs_to_schedule:
                scheduled_encoder_inputs[request.request_id] = (
                    encoder_inputs_to_schedule)
                # Allocate the encoder cache.
                for i in encoder_inputs_to_schedule:
                    self.encoder_cache_manager.allocate(request, i)
                encoder_compute_budget = new_encoder_compute_budget

        # Record the LoRAs in scheduled_running_reqs
        scheduled_loras: set[int] = set()
        if self.lora_config:
            scheduled_loras = set(
                req.lora_request.lora_int_id for req in scheduled_running_reqs
                if req.lora_request and req.lora_request.lora_int_id > 0)
            assert len(scheduled_loras) <= self.lora_config.max_loras

        # Use a temporary RequestQueue to collect requests that need to be
        # skipped and put back at the head of the waiting queue later
        skipped_waiting_requests = create_request_queue(self.policy)

        # Next, schedule the WAITING requests.
        if not preempted_reqs:
            while self.waiting and token_budget > 0:
                if len(self.running) == self.max_num_running_reqs:
                    break

                request = self.waiting.peek_request()

                # CONTRACTKV_QUIESCENCE_WAITING_BEGIN
                if _contractkv_shadow_enabled(request):
                    _contractkv_waiting_gate = _contractkv_should_admit_shadow(self, request)
                    if not _contractkv_waiting_gate["admitted"]:
                        if __import__("os").environ.get("CONTRACTKV_PARKING", "1") == "1":
                            self.waiting.pop_request()
                            self.contractkv_shadow_parking.park(request, _contractkv_last_foreground_activity_ns(self) + int(self.idle_grace_ms * 1e6), _contractkv_waiting_gate["reason"])
                            continue
                        self.waiting.pop_request()
                        skipped_waiting_requests.prepend_request(request)
                        continue
                # CONTRACTKV_QUIESCENCE_WAITING_END
                # KVTransfer: skip request if still waiting for remote kvs.
                if request.status == RequestStatus.WAITING_FOR_REMOTE_KVS:
                    is_ready = self._update_waiting_for_remote_kv(request)
                    if is_ready:
                        request.status = RequestStatus.WAITING
                    else:
                        logger.debug(
                            "%s is still in WAITING_FOR_REMOTE_KVS state.",
                            request.request_id)
                        self.waiting.pop_request()
                        skipped_waiting_requests.prepend_request(request)
                        continue

                # Skip request if the structured output request is still waiting
                # for FSM compilation.
                if request.status == RequestStatus.WAITING_FOR_FSM:
                    structured_output_req = request.structured_output_request
                    if structured_output_req and structured_output_req.grammar:
                        request.status = RequestStatus.WAITING
                    else:
                        self.waiting.pop_request()
                        skipped_waiting_requests.prepend_request(request)
                        continue

                # Check that adding the request still respects the max_loras
                # constraint.
                if (self.lora_config and request.lora_request and
                    (len(scheduled_loras) == self.lora_config.max_loras and
                     request.lora_request.lora_int_id not in scheduled_loras)):
                    # Scheduling would exceed max_loras, skip.
                    self.waiting.pop_request()
                    skipped_waiting_requests.prepend_request(request)
                    continue

                num_external_computed_tokens = 0
                load_kv_async = False

                # Get already-cached tokens.
                if request.num_computed_tokens == 0:
                    # Get locally-cached tokens.
                    new_computed_blocks, num_new_local_computed_tokens = \
                        self.kv_cache_manager.get_computed_blocks(
                            request)

                    # Get externally-cached tokens if using a KVConnector.
                    if self.connector is not None:
                        num_external_computed_tokens, load_kv_async = (
                            self.connector.get_num_new_matched_tokens(
                                request, num_new_local_computed_tokens))

                        if num_external_computed_tokens is None:
                            # The request cannot be scheduled because
                            # the KVConnector couldn't determine
                            # the number of matched tokens.
                            self.waiting.pop_request()
                            skipped_waiting_requests.prepend_request(request)
                            continue

                    # Total computed tokens (local + external).
                    num_computed_tokens = (num_new_local_computed_tokens +
                                           num_external_computed_tokens)
                # KVTransfer: WAITING reqs have num_computed_tokens > 0
                # after async KV recvs are completed.
                else:
                    new_computed_blocks = (
                        self.kv_cache_manager.create_empty_block_list())
                    num_new_local_computed_tokens = 0
                    num_computed_tokens = request.num_computed_tokens

                encoder_inputs_to_schedule = None
                new_encoder_compute_budget = encoder_compute_budget

                # KVTransfer: loading remote KV, do not allocate for new work.
                if load_kv_async:
                    assert num_external_computed_tokens > 0
                    num_new_tokens = 0
                # Number of tokens to be scheduled.
                else:
                    # We use `request.num_tokens` instead of
                    # `request.num_prompt_tokens` to consider the resumed
                    # requests, which have output tokens.
                    num_new_tokens = request.num_tokens - num_computed_tokens
                    if (0 < self.scheduler_config.long_prefill_token_threshold
                            < num_new_tokens):
                        num_new_tokens = (
                            self.scheduler_config.long_prefill_token_threshold)
                    # CONTRACTKV_EPHEMERAL_SHADOW_WAITING_BEGIN
                    _contractkv_waiting_shadow_chunk = _contractkv_shadow_granted_tokens(request)
                    if _contractkv_waiting_shadow_chunk is not None:
                        num_new_tokens = min(num_new_tokens, _contractkv_waiting_shadow_chunk)
                    # CONTRACTKV_EPHEMERAL_SHADOW_WAITING_END

                    # chunked prefill has to be enabled explicitly to allow
                    # pooling requests to be chunked
                    if not self.scheduler_config.chunked_prefill_enabled and \
                        num_new_tokens > token_budget:
                        self.waiting.pop_request()
                        skipped_waiting_requests.prepend_request(request)
                        continue

                    num_new_tokens = min(num_new_tokens, token_budget)
                    assert num_new_tokens > 0

                    # Schedule encoder inputs.
                    if request.has_encoder_inputs:
                        (encoder_inputs_to_schedule, num_new_tokens,
                         new_encoder_compute_budget
                         ) = self._try_schedule_encoder_inputs(
                             request, num_computed_tokens, num_new_tokens,
                             encoder_compute_budget)
                        if num_new_tokens == 0:
                            # The request cannot be scheduled.
                            break

                # Handles an edge case when P/D Disaggregation
                # is used with Spec Decoding where an
                # extra block gets allocated which
                # creates a mismatch between the number
                # of local and remote blocks.
                effective_lookahead_tokens = (0 if request.num_computed_tokens
                                              == 0 else
                                              self.num_lookahead_tokens)

                # Determine if we need to allocate cross-attention blocks.
                if self.is_encoder_decoder and request.has_encoder_inputs:
                    # TODO(russellb): For Whisper, we know that the input is
                    # always padded to the maximum length. If we support other
                    # encoder-decoder models, this will need to be updated if we
                    # want to only allocate what is needed.
                    assert ("whisper"
                            in self.vllm_config.model_config.model.lower()), (
                                "Whisper is the only supported "
                                "encoder-decoder model.")
                    num_encoder_tokens = MULTIMODAL_REGISTRY.\
                        get_encdec_max_encoder_len(
                        self.vllm_config.model_config)
                else:
                    num_encoder_tokens = 0

                new_blocks = self.kv_cache_manager.allocate_slots(
                    request,
                    num_new_tokens + num_external_computed_tokens,
                    num_new_local_computed_tokens,
                    new_computed_blocks,
                    num_lookahead_tokens=effective_lookahead_tokens,
                    delay_cache_blocks=(load_kv_async or _contractkv_pstp_enabled(request)),
                    num_encoder_tokens=num_encoder_tokens,
                )

                if new_blocks is None:
                    # The request cannot be scheduled.
                    break

                # KVTransfer: the connector uses this info to determine
                # if a load is needed. Note that
                # This information is used to determine if a load is
                # needed for this request.
                if self.connector is not None:
                    self.connector.update_state_after_alloc(
                        request,
                        new_computed_blocks + new_blocks,
                        num_external_computed_tokens,
                    )

                # Request was already popped from self.waiting
                # unless it was re-added above due to new_blocks being None.
                request = self.waiting.pop_request()
                if load_kv_async:
                    # If loading async, allocate memory and put request
                    # into the WAITING_FOR_REMOTE_KV state.
                    skipped_waiting_requests.prepend_request(request)
                    request.status = RequestStatus.WAITING_FOR_REMOTE_KVS
                    continue

                req_index += 1
                self.running.append(request)
                # CONTRACTKV_QUIESCENCE_ADMISSION_CALL
                _contractkv_record_admission(self, request)
                if self.log_stats:
                    request.record_event(EngineCoreEventType.SCHEDULED,
                                         scheduled_timestamp)
                if request.status == RequestStatus.WAITING:
                    scheduled_new_reqs.append(request)
                elif request.status == RequestStatus.PREEMPTED:
                    scheduled_resumed_reqs.append(request)
                else:
                    raise RuntimeError(
                        f"Invalid request status: {request.status}")

                if self.lora_config and request.lora_request:
                    scheduled_loras.add(request.lora_request.lora_int_id)
                req_to_new_blocks[request.request_id] = (
                    self.kv_cache_manager.get_blocks(request.request_id))
                num_scheduled_tokens[request.request_id] = num_new_tokens
                token_budget -= num_new_tokens
                request.status = RequestStatus.RUNNING
                request.num_computed_tokens = num_computed_tokens
                # Count the number of prefix cached tokens.
                if request.num_cached_tokens < 0:
                    request.num_cached_tokens = num_computed_tokens
                # Encoder-related.
                if encoder_inputs_to_schedule:
                    scheduled_encoder_inputs[request.request_id] = (
                        encoder_inputs_to_schedule)
                    # Allocate the encoder cache.
                    for i in encoder_inputs_to_schedule:
                        self.encoder_cache_manager.allocate(request, i)
                    encoder_compute_budget = new_encoder_compute_budget

        # Put back any skipped requests at the head of the waiting queue
        if skipped_waiting_requests:
            self.waiting.prepend_requests(skipped_waiting_requests)

        # Check if the scheduling constraints are satisfied.
        total_num_scheduled_tokens = sum(num_scheduled_tokens.values())
        assert total_num_scheduled_tokens <= self.max_num_scheduled_tokens
        assert token_budget >= 0
        assert len(self.running) <= self.max_num_running_reqs
        # Since some requests in the RUNNING queue may not be scheduled in
        # this step, the total number of scheduled requests can be smaller than
        # len(self.running).
        assert (len(scheduled_new_reqs) + len(scheduled_resumed_reqs) +
                len(scheduled_running_reqs) <= len(self.running))

        # Get the longest common prefix among all requests in the running queue.
        # This can be potentially used for cascade attention.
        num_common_prefix_blocks = [0] * len(
            self.kv_cache_config.kv_cache_groups)
        if self.running:
            any_request = self.running[0]
            num_common_prefix_blocks = (
                self.kv_cache_manager.get_num_common_prefix_blocks(
                    any_request, len(self.running)))

        # Construct the scheduler output.
        new_reqs_data = [
            NewRequestData.from_request(
                req, req_to_new_blocks[req.request_id].get_block_ids())
            for req in scheduled_new_reqs
        ]
        cached_reqs_data = self._make_cached_request_data(
            scheduled_running_reqs,
            scheduled_resumed_reqs,
            num_scheduled_tokens,
            scheduled_spec_decode_tokens,
            req_to_new_blocks,
        )
        structured_output_request_ids, grammar_bitmask = (
            self.get_grammar_bitmask(self.running,
                                     scheduled_spec_decode_tokens))
        scheduler_output = SchedulerOutput(
            scheduled_new_reqs=new_reqs_data,
            scheduled_cached_reqs=cached_reqs_data,
            num_scheduled_tokens=num_scheduled_tokens,
            total_num_scheduled_tokens=total_num_scheduled_tokens,
            scheduled_spec_decode_tokens=scheduled_spec_decode_tokens,
            scheduled_encoder_inputs=scheduled_encoder_inputs,
            num_common_prefix_blocks=num_common_prefix_blocks,
            # finished_req_ids is an existing state in the scheduler,
            # instead of being newly scheduled in this step.
            # It contains the request IDs that are finished in between
            # the previous and the current steps.
            finished_req_ids=self.finished_req_ids,
            free_encoder_mm_hashes=self.encoder_cache_manager.
            get_freed_mm_hashes(),
            structured_output_request_ids=structured_output_request_ids,
            grammar_bitmask=grammar_bitmask,
        )

        # NOTE(Kuntai): this function is designed for multiple purposes:
        # 1. Plan the KV cache store
        # 2. Wrap up all the KV cache load / save ops into an opaque object
        # 3. Clear the internal states of the connector
        if self.connector is not None:
            meta = self.connector.build_connector_meta(scheduler_output)
            scheduler_output.kv_connector_metadata = meta

        # collect KV cache events from KV cache manager
        events = self.kv_cache_manager.take_events()

        # collect KV cache events from connector
        if self.connector is not None:
            connector_events = self.connector.take_events()
            if connector_events:
                if events is None:
                    events = list(connector_events)
                else:
                    events.extend(connector_events)

        # publish collected KV cache events
        if events:
            batch = KVEventBatch(ts=time.time(), events=events)
            self.kv_event_publisher.publish(batch)

        # CONTRACTKV_QUIESCENCE_END_ROUND_CALL
        _contractkv_end_round(self, scheduler_output)
        # CONTRACTKV_PREFIX_METRICS_CALL_BEGIN
        _contractkv_prefix_metrics_log_scheduler(self, scheduler_output)
        # CONTRACTKV_PREFIX_METRICS_CALL_END
        self._update_after_schedule(scheduler_output)
        return scheduler_output

    def _update_after_schedule(
        self,
        scheduler_output: SchedulerOutput,
    ) -> None:
        # Advance the number of computed tokens for the request AFTER
        # the request is scheduled.
        # 1. The scheduler_output of the current step has to include the
        #    original number of scheduled tokens to determine input IDs.
        # 2. Advance the number of computed tokens here allowing us to
        #    schedule the prefill request again immediately in the next
        #    scheduling step.
        # 3. If some tokens (e.g. spec tokens) are rejected later, the number of
        #    computed tokens will be adjusted in update_from_output.
        num_scheduled_tokens = scheduler_output.num_scheduled_tokens
        for req_id, num_scheduled_token in num_scheduled_tokens.items():
            request = self.requests[req_id]
            request.num_computed_tokens += num_scheduled_token

            # NOTE: _free_encoder_inputs relies on num_computed_tokens, which
            # may be updated again in _update_from_output for speculative
            # decoding. However, it is safe to call the method here because
            # encoder inputs are always part of the prompt, not the output,
            # and thus are unaffected by speculative decoding.
            if request.has_encoder_inputs:
                self._free_encoder_inputs(request)

        # Clear the finished request IDs.
        # NOTE: We shouldn't do self.finished_req_ids.clear() here because
        # it will also affect the scheduler output.
        self.finished_req_ids = set()

    def _make_cached_request_data(
        self,
        running_reqs: list[Request],
        resumed_reqs: list[Request],
        num_scheduled_tokens: dict[str, int],
        spec_decode_tokens: dict[str, list[int]],
        req_to_new_blocks: dict[str, KVCacheBlocks],
    ) -> CachedRequestData:
        req_ids: list[str] = []
        new_token_ids: list[list[int]] = []
        new_block_ids: list[Optional[tuple[list[int], ...]]] = []
        num_computed_tokens: list[int] = []

        use_connector = self.connector is not None
        for req in itertools.chain(running_reqs, resumed_reqs):
            req_id = req.request_id
            req_ids.append(req_id)
            num_tokens = (num_scheduled_tokens[req_id] -
                          len(spec_decode_tokens.get(req_id, ())))
            if self.use_pp:
                # When using PP, the scheduler sends the sampled tokens back,
                # because there's no direct communication between the first-
                # stage worker and the last-stage worker. Otherwise, we don't
                # need to send the sampled tokens back because the model runner
                # will cache them.
                token_ids = req.all_token_ids[req.num_computed_tokens:req.
                                              num_computed_tokens + num_tokens]
                new_token_ids.append(token_ids)
            elif use_connector:
                # When using a KVConnector, we add a placeholder to avoid index
                # out of bounds errors. TODO: Remove this once the KVConnector
                # is updated to handle token IDs properly.
                new_token_ids.append([])
            new_block_ids.append(
                req_to_new_blocks[req_id].get_block_ids(allow_none=True))
            num_computed_tokens.append(req.num_computed_tokens)
        # Because resumed_reqs is usually empty, it is more efficient to do
        # in-place appending so that we don't need to allocate a new list.
        resumed_from_preemption = [False] * len(running_reqs)
        resumed_from_preemption += [True] * len(resumed_reqs)

        return CachedRequestData(
            req_ids=req_ids,
            resumed_from_preemption=resumed_from_preemption,
            new_token_ids=new_token_ids,
            new_block_ids=new_block_ids,
            num_computed_tokens=num_computed_tokens,
        )

    def _try_schedule_encoder_inputs(
        self,
        request: Request,
        num_computed_tokens: int,
        num_new_tokens: int,
        encoder_compute_budget: int,
    ) -> tuple[list[int], int, int]:
        """
        Determine which encoder inputs need to be scheduled in the current step,
        and update `num_new_tokens` and encoder token budget accordingly.

        An encoder input will be scheduled if:
        - Its output tokens overlap with the range of tokens being computed
        in this step, i.e.,
        [num_computed_tokens, num_computed_tokens + num_new_tokens).
        - It is not already computed and stored in the encoder cache.
        - There is sufficient encoder token budget to process it.
        - The encoder cache has space to store it.

        If an encoder input cannot be scheduled due to cache or budget
        limitations, the method adjusts `num_new_tokens` to schedule only the
        decoder tokens up to just before the unschedulable encoder input.

        Note that num_computed_tokens includes both locally cached
        blocks and externally cached blocks (via KVConnector).
        """
        if num_new_tokens == 0 or not request.has_encoder_inputs:
            return [], num_new_tokens, encoder_compute_budget
        encoder_inputs_to_schedule: list[int] = []
        mm_positions = request.mm_positions
        assert mm_positions is not None
        assert len(mm_positions) > 0

        # NOTE: since scheduler operates on the request level (possibly with
        # multiple encoder inputs per request), we need to create temporary
        # trackers for accounting at the encoder input level.
        mm_hashes_to_schedule = set()
        num_tokens_to_schedule = 0
        for i, pos_info in enumerate(mm_positions):
            start_pos = pos_info.offset
            num_encoder_tokens = pos_info.length

            # The encoder output is needed if the two ranges overlap:
            # [num_computed_tokens, num_computed_tokens + num_new_tokens) and
            # [start_pos, start_pos + num_encoder_tokens)
            if start_pos >= num_computed_tokens + num_new_tokens:
                # The encoder input is not needed in this step.
                break

            if self.is_encoder_decoder and num_computed_tokens > 0:
                assert start_pos == 0, (
                    "Encoder input should be processed at the beginning of "
                    "the sequence when encoder-decoder models are used.")
                # Encoder input has already been computed
                # The calculation here is a bit different. We don't turn encoder
                # output into tokens that get processed by the decoder and
                # reflected in num_computed_tokens. Instead, start_pos reflects
                # the position where we need to ensure we calculate encoder
                # inputs. This should always be 0 to ensure we calculate encoder
                # inputs before running the decoder.  Once we've calculated some
                # decoder tokens (num_computed_tokens > 0), then we know we
                # already calculated encoder inputs and can skip here.
                continue
            elif start_pos + num_encoder_tokens <= num_computed_tokens:
                # The encoder input is already computed and stored
                # in the decoder's KV cache.
                continue

            if not self.is_encoder_decoder:
                # We are not using the encoder cache for encoder-decoder models,
                # yet.
                if request.mm_hashes[i] in mm_hashes_to_schedule:
                    # The same encoder input has already been scheduled in the
                    # current step.
                    continue

                if self.encoder_cache_manager.check_and_update_cache(
                        request, i):
                    # The encoder input is already computed and cached from a
                    # previous step.
                    continue

            # If no encoder input chunking is allowed, we do not want to
            # partially schedule a multimodal item. If the scheduled range would
            # only cover part of the mm input, roll back to before the mm item.
            if (self.scheduler_config.disable_chunked_mm_input
                    and num_computed_tokens < start_pos
                    and (num_computed_tokens + num_new_tokens)
                    < (start_pos + num_encoder_tokens)):
                num_new_tokens = start_pos - num_computed_tokens
                break

            if not self.encoder_cache_manager.can_allocate(
                    request, i, encoder_compute_budget,
                    num_tokens_to_schedule):
                # The encoder cache is full or the encoder budget is exhausted.
                # NOTE(woosuk): We assume that the encoder input tokens should
                # be processed altogether, as the encoder usually uses
                # bidirectional attention.
                if num_computed_tokens < start_pos:
                    # We only schedule the decoder tokens just before the
                    # encoder input.
                    num_new_tokens = start_pos - num_computed_tokens
                else:
                    # Because of prefix caching, num_computed_tokens is greater
                    # than start_pos even though its encoder input is not
                    # available. In this case, we can't schedule any token for
                    # the request in this step.
                    num_new_tokens = 0
                break

            num_tokens_to_schedule += num_encoder_tokens
            encoder_compute_budget -= num_encoder_tokens
            mm_hashes_to_schedule.add(request.mm_hashes[i])
            encoder_inputs_to_schedule.append(i)

        return (
            encoder_inputs_to_schedule,
            num_new_tokens,
            encoder_compute_budget,
        )

    def get_grammar_bitmask(
        self,
        requests: list[Request],
        scheduled_spec_decode_tokens: dict[str, list[int]],
    ):
        # NOTE: structured_output_request_ids maps
        # a request's (request that uses structured output)
        # request_id to its index in the batch.
        # This will help us determine to slice the grammar bitmask
        # and only applies valid mask for requests that
        # uses structured decoding.
        structured_output_request_ids: dict[str, int] = {}
        for i, req in enumerate(requests):
            if req.use_structured_output:
                # PERF: in case of chunked prefill,
                # request might not include any new tokens.
                # Therefore, we might introduce some additional
                # cycle to fill in the bitmask, which could be a big no-op.
                structured_output_request_ids[req.request_id] = i

        if not structured_output_request_ids:
            bitmask = None
        else:
            bitmask = self.structured_output_manager.grammar_bitmask(
                self.requests,
                structured_output_request_ids,
                scheduled_spec_decode_tokens,
            )
        return structured_output_request_ids, bitmask

    def update_from_output(
        self,
        scheduler_output: SchedulerOutput,
        model_runner_output: ModelRunnerOutput,
    ) -> dict[int, EngineCoreOutputs]:
        sampled_token_ids = model_runner_output.sampled_token_ids
        logprobs = model_runner_output.logprobs
        prompt_logprobs_dict = model_runner_output.prompt_logprobs_dict
        num_scheduled_tokens = scheduler_output.num_scheduled_tokens
        pooler_outputs = model_runner_output.pooler_output
        num_nans_in_logits = model_runner_output.num_nans_in_logits

        outputs: dict[int, list[EngineCoreOutput]] = defaultdict(list)
        spec_decoding_stats: Optional[SpecDecodingStats] = None

        # NOTE(woosuk): As len(num_scheduled_tokens) can be up to 1K or more,
        # the below loop can be a performance bottleneck. We should do our best
        # to avoid expensive operations inside the loop.
        stopped_running_reqs: set[Request] = set()
        stopped_preempted_reqs: set[Request] = set()
        for req_id, num_tokens_scheduled in num_scheduled_tokens.items():
            assert num_tokens_scheduled > 0
            request = self.requests.get(req_id)
            if request is None:
                # The request is already finished. This can happen if the
                # request is aborted while the model is executing it (e.g.,
                # in pipeline parallelism).
                continue

            req_index = model_runner_output.req_id_to_index[req_id]
            generated_token_ids = sampled_token_ids[
                req_index] if sampled_token_ids else []

            scheduled_spec_token_ids = (
                scheduler_output.scheduled_spec_decode_tokens.get(req_id))
            if scheduled_spec_token_ids:
                num_draft_tokens = len(scheduled_spec_token_ids)
                num_accepted = len(generated_token_ids) - 1
                num_rejected = num_draft_tokens - num_accepted
                # num_computed_tokens represents the number of tokens
                # processed in the current step, considering scheduled
                # tokens and rejections. If some tokens are rejected,
                # num_computed_tokens is decreased by the number of rejected
                # tokens.
                request.num_computed_tokens -= num_rejected
                spec_decoding_stats = self.make_spec_decoding_stats(
                    spec_decoding_stats,
                    num_draft_tokens=num_draft_tokens,
                    num_accepted_tokens=num_accepted)

            stopped = False
            new_logprobs = None
            new_token_ids = generated_token_ids
            kv_transfer_params = None
            status_before_stop = request.status

            # Check for stop and update request status.
            if new_token_ids:
                new_token_ids, stopped = self._update_request_with_output(
                    request, new_token_ids)

            # Stop checking for pooler models.
            pooler_output = None
            if pooler_outputs:
                pooler_output = pooler_outputs[req_index]
                stopped = check_stop(request, self.max_model_len,
                                     pooler_output)

            prompt_logprobs_tensors = prompt_logprobs_dict.get(req_id)
            contractkv_result = None
            if stopped and request.contractkv_verify_spec is not None:
                contractkv_result = self._finalize_contractkv_verify(
                    request, prompt_logprobs_tensors)
                # The compact result is the only cross-process verifier output.
                prompt_logprobs_tensors = None

            if stopped:
                kv_transfer_params = self._free_request(request)
                if status_before_stop == RequestStatus.RUNNING:
                    stopped_running_reqs.add(request)
                else:
                    stopped_preempted_reqs.add(request)

            # Extract sample logprobs if needed.
            if request.sampling_params is not None \
                and request.sampling_params.logprobs is not None and logprobs:
                # NOTE: once we support N tokens per step (spec decode),
                # the outer lists can be of length > 1.
                new_logprobs = logprobs.slice(req_index, req_index + 1)

            if new_token_ids and self.structured_output_manager.should_advance(
                    request):
                # NOTE: structured_output_request
                # should not be None if use_structured_output, we have
                # checked above, so safe to ignore type warning
                request.structured_output_request.grammar.accept_tokens(  # type: ignore[union-attr]
                    req_id, new_token_ids)

            if num_nans_in_logits is not None and req_id in num_nans_in_logits:
                request.num_nans_in_logits = num_nans_in_logits[req_id]

            if contractkv_result is not None:
                outputs[request.client_index].append(
                    EngineCoreOutput(
                        request_id=req_id,
                        new_token_ids=[],
                        finish_reason=request.get_finished_reason(),
                        events=request.take_events(),
                        trace_headers=request.trace_headers,
                        num_cached_tokens=request.num_cached_tokens,
                        contractkv_result=contractkv_result,
                    ))
            elif new_token_ids or pooler_output is not None \
                or kv_transfer_params:

                # Add EngineCoreOutput for this Request.
                outputs[request.client_index].append(
                    EngineCoreOutput(
                        request_id=req_id,
                        new_token_ids=new_token_ids,
                        finish_reason=request.get_finished_reason(),
                        new_logprobs=new_logprobs,
                        new_prompt_logprobs_tensors=prompt_logprobs_tensors,
                        pooling_output=pooler_output,
                        stop_reason=request.stop_reason,
                        events=request.take_events(),
                        kv_transfer_params=kv_transfer_params,
                        trace_headers=request.trace_headers,
                        num_cached_tokens=request.num_cached_tokens,
                    ))
            else:
                # Invariant: EngineCore returns no partial prefill outputs.
                assert not prompt_logprobs_tensors

        # Remove the stopped requests from the running and waiting queues.
        if stopped_running_reqs:
            self.running = remove_all(self.running, stopped_running_reqs)
        if stopped_preempted_reqs:
            # This is a rare case and unlikely to impact performance.
            self.waiting.remove_requests(stopped_preempted_reqs)

        # KV Connector: update state for finished KV Transfers.
        if model_runner_output.kv_connector_output:
            self._update_from_kv_xfer_finished(
                model_runner_output.kv_connector_output)

        # Create EngineCoreOutputs for all clients that have requests with
        # outputs in this step.
        engine_core_outputs = {
            client_index: EngineCoreOutputs(outputs=outs)
            for client_index, outs in outputs.items()
        }

        finished_req_ids = self.finished_req_ids_dict
        if finished_req_ids:
            # Include ids of requests that finished since last outputs
            # were sent.
            for client_index, finished_set in finished_req_ids.items():
                # Set finished request set in EngineCoreOutputs for this client.
                if (eco := engine_core_outputs.get(client_index)) is not None:
                    eco.finished_requests = finished_set
                else:
                    engine_core_outputs[client_index] = EngineCoreOutputs(
                        finished_requests=finished_set)
            finished_req_ids.clear()

        if (stats := self.make_stats(spec_decoding_stats)) is not None:
            # Return stats to only one of the front-ends.
            if (eco := next(iter(engine_core_outputs.values()), None)) is None:
                # We must return the stats even if there are no request
                # outputs this step.
                engine_core_outputs[0] = eco = EngineCoreOutputs()
            eco.scheduler_stats = stats

        return engine_core_outputs

    @staticmethod
    def _contractkv_quantile(values: list[float], fraction: float) -> float:
        if not values:
            return float("nan")
        ordered = sorted(values)
        index = fraction * (len(ordered) - 1)
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        weight = index - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    def _finalize_contractkv_verify(
        self,
        request: Request,
        prompt_logprobs_tensors: Any,
    ) -> ContractKVCompactResult:
        spec = request.contractkv_verify_spec
        assert spec is not None
        decision = "INCOMPLETE"
        state = "ABORTED"
        failure = ""
        committed_tokens = 0
        raw_q05 = float("nan")
        candidate_q05 = float("nan")
        degradation_q95 = float("nan")
        terminal_stop_margin = float("nan")  # CONTRACTKV_PHASE26R_STOP_MARGIN_V1
        certificate_hash = ""
        raw_min = candidate_min = float("nan")
        raw_min_index = candidate_min_index = -1
        minimum_margin_passed = False

        try:
            expected_policy = os.environ.get("CONTRACTKV_POLICY_HASH", "")
            if expected_policy and spec.policy_hash != expected_policy:
                raise ValueError("policy_manifest_mismatch")
            if prompt_logprobs_tensors is None:
                raise ValueError("prompt_logprobs_missing")
            if len(spec.reference_answer_ids) != len(
                    spec.reference_raw_margins):
                raise ValueError("reference_length_mismatch")
            lists = prompt_logprobs_tensors.tolists()
            candidate_margins: list[float] = []
            candidate_ranks: list[int] = []
            answer_start = spec.verify_start_token
            cached_read = int(getattr(request, "contractkv_cached_prefix_read_tokens", 0))
            if cached_read >= answer_start:
                raise ValueError("cached_prefix_overlaps_required_answer_rows")
            for offset, target in enumerate(spec.reference_answer_ids):
                row = answer_start - 1 + offset
                ids = [int(value)
                       for value in lists.logprob_token_ids[row]]
                values = [float(value) for value in lists.logprobs[row]]
                target_values = [value for token_id, value in zip(ids, values)
                                 if token_id == target]
                competitors = [value for token_id, value in zip(ids, values)
                               if token_id != target]
                if not target_values or not competitors:
                    raise ValueError(f"target_unavailable:{offset}")
                candidate_margins.append(target_values[0] - max(competitors))
                candidate_ranks.append(int(lists.sampled_token_ranks[row]))

            stop_row = answer_start - 1 + len(spec.reference_answer_ids)
            stop_rank = int(lists.sampled_token_ranks[stop_row])
            stop_ids = [int(value)
                        for value in lists.logprob_token_ids[stop_row]]
            stop_values = [float(value)
                           for value in lists.logprobs[stop_row]]
            stop_targets = [value for token_id, value in zip(
                stop_ids, stop_values)
                            if token_id == spec.terminal_stop_token_id]
            stop_competitors = [value for token_id, value in zip(
                stop_ids, stop_values)
                                if token_id != spec.terminal_stop_token_id]
            if not stop_targets or not stop_competitors:
                raise ValueError("terminal_stop_target_or_competitor_unavailable")
            terminal_stop_margin = stop_targets[0] - max(stop_competitors)
            stop_ok = stop_rank == 1 and spec.terminal_stop_token_id in stop_ids
            raw_q05 = self._contractkv_quantile(
                spec.reference_raw_margins, 0.05)
            candidate_q05 = self._contractkv_quantile(
                candidate_margins, 0.05)
            degradations = [raw - candidate for raw, candidate in zip(
                spec.reference_raw_margins, candidate_margins)]
            degradation_q95 = self._contractkv_quantile(degradations, 0.95)
            min_margin = float(os.environ.get(
                "CONTRACTKV_MIN_CANDIDATE_MARGIN", "0"))
            max_degradation = float(os.environ.get(
                "CONTRACTKV_MAX_DEGRADATION", "4.0"))
            min_stop_margin = float(os.environ.get(
                "CONTRACTKV_MIN_STOP_MARGIN", "-inf"))
            margin_result = minimum_margin_gate(
                spec.reference_raw_margins, candidate_margins, terminal_stop_margin,
                float(os.environ.get("CONTRACTKV_MIN_RAW_TOKEN_MARGIN", "-inf")),
                float(os.environ.get("CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN", "-inf")))
            raw_min = margin_result["raw_margin_min"]
            candidate_min = margin_result["candidate_margin_min"]
            raw_min_index = margin_result["raw_margin_min_index"]
            candidate_min_index = margin_result["candidate_margin_min_index"]
            minimum_margin_passed = margin_result["passed"]
            if os.environ.get("CONTRACTKV_R2_VERIFY_TRACE"):
                emit_trace("CONTRACTKV_R2_VERIFY_TRACE", {
                    "event": "r2_actual_verify_answer_eos_rows", "request_id": request.request_id,
                    "verify_start_token": spec.verify_start_token,
                    "reference_answer_ids": spec.reference_answer_ids,
                    "raw_reference_margins": spec.reference_raw_margins,
                    "candidate_ranks": candidate_ranks, "candidate_margins": candidate_margins,
                    "terminal_stop_rank": stop_rank, "terminal_stop_margin": terminal_stop_margin,
                    "pointwise_gate": margin_result})
            if (all(rank == 1 for rank in candidate_ranks) and stop_ok
                    and candidate_q05 >= min_margin
                    and degradation_q95 <= max_degradation
                    and terminal_stop_margin >= min_stop_margin
                    and minimum_margin_passed):
                decision = "PASS"
                state = "COMMITTED"
                committed_tokens = min(
                    spec.stable_prefix_end_token,
                    request.num_computed_tokens,
                )
                committed_tokens -= committed_tokens % self.block_size
                if committed_tokens <= 0:
                    decision = "INCOMPLETE"
                    state = "ABORTED"
                    failure = "no_full_block_to_commit"
                    committed_tokens = 0
                else:
                    self.kv_cache_manager.cache_blocks(
                        request, committed_tokens)
                    # Computational prefix permission is separate from query permission.
                    if request.cache_salt:
                        registry = getattr(self.kv_cache_manager,
                                           "contractkv_certified_prefixes", None)
                        if registry is None:
                            registry = {}
                            self.kv_cache_manager.contractkv_certified_prefixes = registry
                        approved = registry.setdefault(
                            (request.cache_salt, spec.policy_hash), {})
                        for index in range(committed_tokens // self.block_size):
                            approved[(index + 1) * self.block_size] = request.block_hashes[index]
            else:
                decision = "FAIL"
                failure = ("pointwise_margin_guard:" + margin_result["reason"]
                           if not minimum_margin_passed else "token_path_or_margin_guard_failed")
        except Exception as exc:
            failure = str(exc)

        certificate_issued = state == "COMMITTED"
        if certificate_issued:
            certificate_payload = "|".join((
                spec.txn_id,
                spec.policy_hash,
                spec.stable_content_hash,
                spec.layout_hash,
                spec.dependency_graph_hash,
                str(committed_tokens),
            ))
            certificate_hash = hashlib.sha256(
                certificate_payload.encode("utf-8")).hexdigest()
        else:
            committed_tokens = 0

        return ContractKVCompactResult(
            txn_id=spec.txn_id,
            policy_hash=spec.policy_hash,
            verify_decision=decision,
            txn_state=state,
            failure_reason=failure,
            committed_tokens=committed_tokens,
            committed_full_blocks=committed_tokens // self.block_size,
            certificate_issued=certificate_issued,
            certificate_hash=certificate_hash,
            raw_margin_q05=raw_q05,
            candidate_margin_q05=candidate_q05,
            degradation_q95=degradation_q95,
            terminal_stop_margin=terminal_stop_margin,
            cached_prefix_read_tokens=int(getattr(request, "contractkv_cached_prefix_read_tokens", 0)),
            raw_margin_min=raw_min, candidate_margin_min=candidate_min,
            raw_margin_min_index=raw_min_index, candidate_margin_min_index=candidate_min_index,
            minimum_margin_guard_passed=minimum_margin_passed,
        )

    def _update_request_with_output(
        self,
        request: Request,
        new_token_ids: list[int],
    ) -> tuple[list[int], bool]:
        # Append generated tokens and check for stop. Note that if
        # a request is still being prefilled, we expect the model runner
        # to return empty token ids for the request.
        stopped = False
        for num_new, output_token_id in enumerate(new_token_ids, 1):
            request.append_output_token_ids(output_token_id)

            # Check for stop and update request state.
            # This must be called before we make the EngineCoreOutput.
            stopped = check_stop(request, self.max_model_len)
            if stopped:
                del new_token_ids[num_new:]  # Trim new tokens if needed.
                break
        return new_token_ids, stopped

    def _free_encoder_inputs(self, request: Request) -> None:
        cached_encoder_input_ids = (
            self.encoder_cache_manager.get_cached_input_ids(request))
        # OPTIMIZATION: Avoid list(set) if the set is empty.
        if not cached_encoder_input_ids:
            return

        # Here, we use list(set) to avoid modifying the set while iterating
        # over it.
        for input_id in list(cached_encoder_input_ids):
            mm_positions = request.mm_positions[input_id]
            start_pos = mm_positions.offset
            num_tokens = mm_positions.length
            if self.is_encoder_decoder and request.num_computed_tokens > 0:
                # With Whisper, as soon as we've generated a single token,
                # we know we're done with the encoder input. Cross Attention
                # KVs have been calculated and cached already.
                self.encoder_cache_manager.free_encoder_input(
                    request, input_id)
            elif start_pos + num_tokens <= request.num_computed_tokens:
                # The encoder output is already processed and stored
                # in the decoder's KV cache.
                self.encoder_cache_manager.free_encoder_input(
                    request, input_id)

    def update_draft_token_ids(
        self,
        draft_token_ids: DraftTokenIds,
    ) -> None:
        for req_id, spec_token_ids in zip(
                draft_token_ids.req_ids,
                draft_token_ids.draft_token_ids,
        ):
            request = self.requests.get(req_id)
            if request is None or request.is_finished():
                # The request may have been finished. Skip.
                continue

            # Add newly generated spec token ids to the request.
            if not spec_token_ids:
                # NOTE(woosuk): request.spec_token_ids should be updated.
                request.spec_token_ids.clear()
            elif self.structured_output_manager.should_advance(request):
                metadata = request.structured_output_request
                request.spec_token_ids = metadata.grammar.validate_tokens(  # type: ignore[union-attr]
                    spec_token_ids)
            else:
                request.spec_token_ids = spec_token_ids

    def get_request_counts(self) -> tuple[int, int]:
        """Returns (num_running_reqs, num_waiting_reqs)."""
        return len(self.running), len(self.waiting)

    def add_request(self, request: Request) -> None:
        # CONTRACTKV_PSTP_ADD_REQUEST_CALL
        _contractkv_attach_pstp(request)
        _contractkv_record_arrival(self, request)
        self.waiting.add_request(request)
        self.requests[request.request_id] = request
        if self.log_stats:
            request.record_event(EngineCoreEventType.QUEUED)

    def finish_requests(
        self,
        request_ids: Union[str, Iterable[str]],
        finished_status: RequestStatus,
    ) -> None:
        """Handles the finish signal from outside the scheduler.

        For example, the API server can abort a request when the client
        disconnects.
        """
        assert RequestStatus.is_finished(finished_status)
        if isinstance(request_ids, str):
            request_ids = (request_ids, )
        else:
            request_ids = set(request_ids)

        running_requests_to_remove = set()
        waiting_requests_to_remove = []
        valid_requests = []

        # First pass: collect requests to remove from queues
        for req_id in request_ids:
            request = self.requests.get(req_id)
            if request is None:
                # Invalid request ID.
                continue

            valid_requests.append(request)
            if request.status == RequestStatus.RUNNING:
                running_requests_to_remove.add(request)
            else:
                waiting_requests_to_remove.append(request)

        # Remove all requests from queues at once for better efficiency
        if running_requests_to_remove:
            self.running = remove_all(self.running, running_requests_to_remove)
        if waiting_requests_to_remove:
            self.waiting.remove_requests(waiting_requests_to_remove)

        # Second pass: set status and free requests
        for request in valid_requests:
            request.status = finished_status
            self._free_request(request)

    def _free_request(self, request: Request) -> Optional[dict[str, Any]]:
        assert request.is_finished()

        # CONTRACTKV_QUIESCENCE_COMPLETION_CALL
        _contractkv_record_completion(self, request)
        # CONTRACTKV_EPHEMERAL_SHADOW_FINALIZE_CALL
        _contractkv_pstp_finalize(self, request)
        delay_free_blocks, kv_xfer_params = self._connector_finished(request)
        self.encoder_cache_manager.free(request)
        request_id = request.request_id
        self.finished_req_ids.add(request_id)
        if self.finished_req_ids_dict is not None:
            self.finished_req_ids_dict[request.client_index].add(request_id)

        if not delay_free_blocks:
            self._free_blocks(request)

        return kv_xfer_params

    def _free_blocks(self, request: Request):
        assert request.is_finished()
        self.kv_cache_manager.free(request)
        del self.requests[request.request_id]

    def get_num_unfinished_requests(self) -> int:
        parked = len(getattr(getattr(self, 'contractkv_shadow_parking', None), 'items', {}))
        return len(self.waiting) + len(self.running) + parked

    def has_finished_requests(self) -> bool:
        return len(self.finished_req_ids) > 0

    def reset_prefix_cache(self) -> bool:
        return self.kv_cache_manager.reset_prefix_cache()

    def make_stats(
        self,
        spec_decoding_stats: Optional[SpecDecodingStats] = None,
    ) -> Optional[SchedulerStats]:
        if not self.log_stats:
            return None
        prefix_cache_stats = self.kv_cache_manager.make_prefix_cache_stats()
        assert prefix_cache_stats is not None
        return SchedulerStats(
            num_running_reqs=len(self.running),
            num_waiting_reqs=len(self.waiting),
            kv_cache_usage=self.kv_cache_manager.usage,
            prefix_cache_stats=prefix_cache_stats,
            spec_decoding_stats=spec_decoding_stats,
            num_corrupted_reqs=sum(req.is_output_corrupted
                                   for req in self.running),
        )

    def make_spec_decoding_stats(
        self,
        spec_decoding_stats: Optional[SpecDecodingStats],
        num_draft_tokens: int,
        num_accepted_tokens: int,
    ) -> Optional[SpecDecodingStats]:
        if not self.log_stats:
            return None
        if spec_decoding_stats is None:
            spec_decoding_stats = SpecDecodingStats.new(self.num_spec_tokens)
        spec_decoding_stats.observe_draft(
            num_draft_tokens=num_draft_tokens,
            num_accepted_tokens=num_accepted_tokens)
        return spec_decoding_stats

    def shutdown(self) -> None:
        if self.kv_event_publisher:
            self.kv_event_publisher.shutdown()
        if self.connector is not None:
            self.connector.shutdown()

    ########################################################################
    # KV Connector Related Methods
    ########################################################################

    def get_kv_connector(self) -> Optional[KVConnectorBase_V1]:
        return self.connector

    def _connector_finished(
            self, request: Request) -> tuple[bool, Optional[dict[str, Any]]]:
        """
        Invoke the KV connector request_finished() method if applicable.

        Returns optional kv transfer parameters to be included with the
        request outputs.
        """
        if self.connector is None:
            return False, None

        (block_ids, ) = self.kv_cache_manager.get_block_ids(request.request_id)
        return self.connector.request_finished(request, block_ids)

    def _update_waiting_for_remote_kv(self, request: Request) -> bool:
        """
        KV Connector: check if the request_id is finished_recving.

        The finished_recving_kv_req_ids list is populated
        on the previous steps()'s update_from_output based
        on the worker side connector.

        When the kv transfer is ready, we cache the blocks
        and the request state will be moved back to WAITING from
        WAITING_FOR_REMOTE_KV.
        """
        assert self.connector is not None
        if request.request_id not in self.finished_recving_kv_req_ids:
            return False

        # Now that the blocks are ready, actually cache them.
        (block_ids, ) = self.kv_cache_manager.get_block_ids(request.request_id)
        num_computed_tokens = len(block_ids) * self.block_size
        # Handle the case where num request tokens less than one block.
        num_computed_tokens = min(num_computed_tokens, request.num_tokens)
        if num_computed_tokens == request.num_tokens:
            num_computed_tokens -= 1
        # This will cache the blocks iff caching is enabled.
        self.kv_cache_manager.cache_blocks(request, num_computed_tokens)

        # Update the request state for scheduling.
        request.num_computed_tokens = num_computed_tokens

        # Return that we are ready.
        self.finished_recving_kv_req_ids.remove(request.request_id)
        return True

    def _update_from_kv_xfer_finished(self,
                                      kv_connector_output: KVConnectorOutput):
        """
        KV Connector: update the scheduler state based on the output.

        The Worker side connectors add finished_recving and
        finished_sending reqs to the output.
        * if finished_sending: free the blocks
        # if finished_recving: add to state so we can
            schedule the request during the next step.
        """

        if self.connector is not None:
            self.connector.update_connector_output(kv_connector_output)

        # KV Connector:: update recv and send status from last step.
        for req_id in (kv_connector_output.finished_recving or ()):
            logger.debug("Finished recving KV transfer for request %s", req_id)
            self.finished_recving_kv_req_ids.add(req_id)
        for req_id in (kv_connector_output.finished_sending or ()):
            logger.debug("Finished sending KV transfer for request %s", req_id)
            self._free_blocks(self.requests[req_id])
