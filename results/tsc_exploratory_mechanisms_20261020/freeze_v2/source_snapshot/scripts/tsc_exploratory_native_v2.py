"""v1 mechanism plus release evidence for abort/cancel integration controls."""
from scripts.tsc_exploratory_native_v1 import *


def audit_native_release(scheduler, request):
    try:
        ids = [i for g in scheduler.kv_cache_manager.get_block_ids(request.request_id) for i in g]
        blocks = [scheduler.kv_cache_manager.block_pool.blocks[i] for i in ids]
        emit("native_candidate_release", request_id=request.request_id,
             txn_id=request.contractkv_verify_spec.txn_id,
             actual_status=getattr(request.status, "name", str(request.status)),
             allocated_blocks=len(blocks), cached_blocks_before_release=sum(b.block_hash is not None for b in blocks),
             ref_counts=[b.ref_cnt for b in blocks])
    except Exception as exc:
        emit("native_release_probe_error", request_id=request.request_id, error=repr(exc))
