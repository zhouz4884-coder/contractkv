"""Opt-in development hooks: actual decode attestation and revocable cache priority.

Never imported by the default runtime. No reference-count pinning, fake request,
extra prefetch, answer lookup, or relaxation of the existing verifier floors.
"""
from collections import OrderedDict
import hashlib
import json
import os
import time
from types import SimpleNamespace

MODE = "fused-free-generation-qa128-v1"


def emit(kind, **data):
    path = os.environ.get("CONTRACTKV_EXPLORATORY_TRACE")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(event=kind, monotonic_s=time.perf_counter(), **data),
                               ensure_ascii=False, allow_nan=False) + "\n")


def is_fused(request):
    return getattr(getattr(request, "contractkv_verify_spec", None), "attestation_mode", None) == MODE


def collect(request, generated_ids, logprobs, req_index):
    if not is_fused(request):
        return
    trace = getattr(request, "_exploratory_decode", None)
    if trace is None:
        trace = request._exploratory_decode = []
    if not generated_ids:
        return
    # Speculative decoding is not enabled in this experiment. Fail closed if
    # output shape differs; never substitute logprobs from another execution.
    if logprobs is None or len(generated_ids) != 1:
        request._exploratory_decode_error = "missing_logprobs_or_multi_token_step"
        return
    rows = logprobs.slice(req_index, req_index + 1)
    if hasattr(rows, "tolists"):
        rows = rows.tolists()
    if len(rows.logprobs) != 1 or len(rows.sampled_token_ranks) != 1:
        request._exploratory_decode_error = "decode_logprob_shape"
        return
    trace.append(dict(token_id=int(generated_ids[0]),
                      top_ids=[int(v) for v in rows.logprob_token_ids[0]],
                      logprobs=[float(v) for v in rows.logprobs[0]],
                      rank=int(rows.sampled_token_ranks[0])))


class IndexedDecodeRows:
    """Index actual decode rows using the old verifier's answer-row offsets.

    This is a view of observed decode data, not reconstructed teacher-forced
    logits. No padding rows or numerical values are synthesized.
    """
    def __init__(self, rows, start, key):
        self.rows, self.start, self.key = rows, start, key

    def __getitem__(self, index):
        offset = index - self.start
        if offset < 0 or offset >= len(self.rows):
            raise IndexError("unobserved_decode_row")
        return self.rows[offset][self.key]


def fused_rows(request):
    spec = request.contractkv_verify_spec
    rows = getattr(request, "_exploratory_decode", [])
    actual = [r["token_id"] for r in rows]
    expected = list(spec.reference_answer_ids) + [spec.terminal_stop_token_id]
    status = getattr(request.status, "name", str(request.status))
    emit("fused_actual_trajectory", request_id=request.request_id,
         prompt_token_ids=list(request.prompt_token_ids), actual_output_token_ids=actual,
         reference_output_token_ids=expected, actual_status=status, rows=rows,
         error=getattr(request, "_exploratory_decode_error", None),
         shared_publication_decided=False)
    if getattr(request, "_exploratory_decode_error", None):
        raise ValueError(request._exploratory_decode_error)
    if status != "FINISHED_STOPPED" or actual != expected:
        raise ValueError("actual_free_generation_ID_or_EOS_mismatch")
    if len(rows) != len(expected) or not rows:
        raise ValueError("actual_decode_evidence_incomplete")
    start = spec.verify_start_token - 1
    value = SimpleNamespace(logprob_token_ids=IndexedDecodeRows(rows, start, "top_ids"),
                            logprobs=IndexedDecodeRows(rows, start, "logprobs"),
                            sampled_token_ranks=IndexedDecodeRows(rows, start, "rank"))
    return SimpleNamespace(tolists=lambda: value)


def actual_fields(request):
    if not is_fused(request):
        return dict(fused_prompt_ids=None, fused_output_ids=None, fused_finish=None)
    status = getattr(request.status, "name", str(request.status))
    return dict(fused_prompt_ids=list(request.prompt_token_ids),
                fused_output_ids=[r["token_id"] for r in getattr(request, "_exploratory_decode", [])],
                fused_finish="stop" if status == "FINISHED_STOPPED" else status)


def groups(pool):
    if not hasattr(pool, "_exploratory_priority"):
        pool._exploratory_priority = OrderedDict()
    now = time.monotonic()
    for key in list(pool._exploratory_priority):
        if pool._exploratory_priority[key]["expires"] <= now:
            del pool._exploratory_priority[key]
    return pool._exploratory_priority


def mark(scheduler, request, tokens, certified):
    mode = os.environ.get("CONTRACTKV_EXPLORATORY_RESIDENCY", "OFF")
    if mode != ("CERTIFIED" if certified else "GENERIC"):
        return
    pool = scheduler.kv_cache_manager.block_pool
    # Single KV group only, matching the frozen FP16 7B/8B runtime.
    from vllm.v1.core.kv_cache_utils import make_block_hash_with_group_id
    hashes = [make_block_hash_with_group_id(h, 0) for h in
              request.block_hashes[:tokens // scheduler.block_size]]
    existing = [h for h in hashes if h in pool.cached_block_hash_to_block]
    cap = int((pool.num_gpu_blocks - 1) * .75)
    selected = existing[:cap]
    key = hashlib.sha256((str(request.cache_salt) + ":" + str(hashes[:1])).encode()).hexdigest()
    current = groups(pool) if os.environ.get("CONTRACTKV_EXPLORATORY_RESIDENCY", "OFF") != "OFF" else {}
    current.pop(key, None)
    while current and sum(len(v["hashes"]) for v in current.values()) + len(selected) > cap:
        current.popitem(last=False)
    current[key] = dict(hashes=set(selected), expires=time.monotonic() + 120.)
    emit("priority_group", request_id=request.request_id, certified=certified,
         requested_blocks=len(hashes), existing_blocks=len(existing), kept_blocks=len(selected),
         budget_blocks=cap, groups=len(current), priority_blocks=sum(len(v["hashes"]) for v in current.values()),
         pool_blocks=pool.num_gpu_blocks, ref_counts_unchanged=True)


def generic_before_free(scheduler, request):
    if getattr(request, "contractkv_verify_spec", None) is None:
        mark(scheduler, request, min(len(request.prompt_token_ids), request.num_computed_tokens), False)


def allocate(pool, count):
    """Choose reusable free blocks with a bounded, revocable second chance.

    If all available blocks have priority, reclaim them normally. Active blocks
    are never in this queue; no ref_cnt is changed here and no capacity is hidden.
    """
    current = groups(pool)
    protected = set().union(*(v["hashes"] for v in current.values())) if current else set()
    selected = []
    scanned = skipped = 0
    available = pool.get_num_free_blocks()
    while len(selected) < count and scanned < available:
        block = pool.free_block_queue.popleft()
        scanned += 1
        if block.block_hash in protected and count - len(selected) < available - scanned + 1:
            pool.free_block_queue.append(block)
            skipped += 1
        else:
            selected.append(block)
    if len(selected) < count:
        selected.extend(pool.free_block_queue.popleft_n(count - len(selected)))
    assert len(selected) == count and all(b.ref_cnt == 0 for b in selected)
    emit("allocate", requested_blocks=count, free_blocks_before=available,
         priority_candidates=len(protected), skipped_priority=skipped,
         evicted_hashes=[repr(b.block_hash) for b in selected if b.block_hash is not None],
         priority_evictions=sum(b.block_hash in protected for b in selected),
         pool_blocks=pool.num_gpu_blocks)
    return selected
