#!/usr/bin/env python3
"""Install verification-driven PSTP overrides into the vLLM V1 scheduler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.install_vllm_v1_ephemeral_shadow_hook import (
    HELPER_END,
    install as install_phase16r,
    strip_region,
)


HELPER_BEGIN = "# CONTRACTKV_PHASE17_HELPER_BEGIN"
HELPER_END_17 = "# CONTRACTKV_PHASE17_HELPER_END"
RECEIVE_BEGIN = "# CONTRACTKV_PHASE17_RECEIVE_BEGIN"
RECEIVE_END = "# CONTRACTKV_PHASE17_RECEIVE_END"
POST_CLEANUP_BEGIN = "# CONTRACTKV_PHASE17_POST_CLEANUP_BEGIN"
POST_CLEANUP_END = "# CONTRACTKV_PHASE17_POST_CLEANUP_END"


HELPER = r'''# CONTRACTKV_PHASE17_HELPER_BEGIN
def _contractkv_policy_errors(runtime):
    try:
        from scripts.contractkv_frozen_policy import FrozenVerifierPolicy, RuntimeIdentity, policy_hash, validate_policy_runtime
        payload = runtime.verify_payload
        policy = FrozenVerifierPolicy(**dict(payload.get("frozen_policy") or {}))
        identity = RuntimeIdentity(**dict(runtime.plan.runtime_identity or {}))
        errors = validate_policy_runtime(policy, identity)
        if runtime.plan.policy_hash != policy_hash(policy):
            errors.append("runtime policy_hash differs from manifest")
        return errors
    except Exception as exc:
        return ["policy_loader_error=" + repr(exc)]


def _contractkv_scope_errors(runtime):
    try:
        from scripts.contractkv_certificate_scope import (
            CertificateValidityScope, RequestValidityContext, validation_errors)
        model_identity = runtime.plan.model_identity
        certificate_scope = CertificateValidityScope(
            model_identity=model_identity,
            task_family=runtime.plan.task_family,
            layout_hash=runtime.plan.layout_hash,
            stable_prefix_hash=runtime.plan.stable_content_hash,
            scope_mode=runtime.plan.scope_mode,
            observation_identity=runtime.plan.observation_identity,
            observation_epoch=runtime.plan.observation_epoch,
            policy_hash=runtime.plan.policy_hash,
            qualification_hash=runtime.plan.qualification_hash,
        )
        request_scope = RequestValidityContext(
            **dict(runtime.verify_payload.get("request_scope") or {}))
        return validation_errors(certificate_scope, request_scope)
    except Exception as exc:
        return ["scope_loader_error=" + repr(exc)]


def _contractkv_attach_pstp(request):
    runtime = getattr(request, "contractkv_pstp_runtime", None)
    if runtime is not None:
        return runtime
    if getattr(request, "_contractkv_pstp_lookup_done", False):
        return None
    request._contractkv_pstp_lookup_done = True
    try:
        from scripts.contractkv_transaction import lookup_runtime
        runtime = lookup_runtime(str(request.request_id))
        if runtime is None:
            return None
        if runtime.plan.fault_mode == "cancel_before_verification":
            from scripts.contractkv_pstp import VerifyDecision
            runtime.verify_decision = VerifyDecision.CANCELLED
        runtime.policy_errors = _contractkv_policy_errors(runtime)
        runtime.scope_errors = _contractkv_scope_errors(runtime)
        request.contractkv_pstp_runtime = runtime
        _contractkv_write({
            "event": "phase17_runtime_attached",
            "request_id": request.request_id,
            "txn_id": runtime.plan.txn_id,
            "txn_state": runtime.txn_state.value,
            "verify_decision": runtime.verify_decision.value,
            "stable_prefix_end_token": runtime.plan.stable_prefix_end_token,
            "fault_mode": runtime.plan.fault_mode,
            "policy_hash": runtime.plan.policy_hash,
            "policy_version": runtime.plan.policy_version,
            "policy_errors": runtime.policy_errors,
            "scope_errors": runtime.scope_errors,
        })
        return runtime
    except Exception as exc:
        _contractkv_write({"event": "phase17_attach_error", "request_id": getattr(request, "request_id", ""), "error": repr(exc)})
        return None


def _contractkv_pstp_enabled(request):
    return _contractkv_attach_pstp(request) is not None


def _contractkv_shadow_enabled(request):
    runtime = _contractkv_attach_pstp(request)
    return bool(runtime is not None and runtime.plan.shadow_work)


def _contractkv_phase17_receive_verify_tensors(scheduler, request, tensors):
    runtime = _contractkv_attach_pstp(request)
    if runtime is None or runtime.verify_decision.value != "PENDING":
        return
    from scripts.contractkv_pstp import VerifyDecision
    from scripts.contractkv_transaction import TxnState
    if getattr(runtime, "policy_errors", []):
        from dataclasses import replace
        from scripts.contractkv_verifier import incomplete_report
        runtime.txn_state = TxnState.VERIFYING
        runtime.verify_report = replace(
            incomplete_report("policy_runtime_mismatch: " + "; ".join(runtime.policy_errors)),
            policy_hash=runtime.plan.policy_hash,
            policy_version=runtime.plan.policy_version,
            attestation_mode=runtime.plan.attestation_mode,
        )
        runtime.verify_decision = VerifyDecision.INCOMPLETE
        _contractkv_write({
            "event": "phase17_verify_report", "request_id": request.request_id,
            "txn_id": runtime.plan.txn_id, "decision": runtime.verify_decision.value,
            "failure_reason": runtime.verify_report.failure_reason,
            "policy_hash": runtime.plan.policy_hash,
        })
        return
    if runtime.plan.fault_mode == "cancel_during_verification":
        runtime.verify_decision = VerifyDecision.CANCELLED
        runtime.txn_state = TxnState.VERIFYING
        return
    if runtime.plan.fault_mode in {"missing_report", "frontend_disconnect"}:
        return
    runtime.txn_state = TxnState.VERIFYING
    if tensors is None:
        runtime.verify_decision = VerifyDecision.INCOMPLETE
        _contractkv_write({
            "event": "phase17_verify_report",
            "request_id": request.request_id,
            "txn_id": runtime.plan.txn_id,
            "decision": runtime.verify_decision.value,
            "failure_reason": "prompt_logprobs missing before cleanup",
        })
        return
    from scripts.contractkv_verifier import report_from_prompt_logprob_tensors
    report = report_from_prompt_logprob_tensors(runtime.verify_payload, tensors)
    runtime.verify_report = report
    runtime.verify_decision = report.decision
    _contractkv_write({
        "event": "phase17_verify_report",
        "request_id": request.request_id,
        "txn_id": runtime.plan.txn_id,
        "decision": report.decision.value,
        "failure_reason": report.failure_reason,
        "answer_tokens": report.answer_tokens,
        "top1_matches": report.top1_matches,
        "stop_consistent": report.stop_consistent,
        "raw_margin_q05": report.raw_margin_q05,
        "candidate_margin_q05": report.candidate_margin_q05,
        "degradation_q95": report.degradation_q95,
        "robustness_reserve": report.robustness_reserve,
        "policy_hash": report.policy_hash,
        "policy_version": report.policy_version,
    })


def _contractkv_pstp_finalize(scheduler, request):
    runtime = _contractkv_attach_pstp(request)
    if runtime is None:
        return
    import time as _time
    from scripts.contractkv_pstp import VerifyDecision, aligned_commit_tokens
    from scripts.contractkv_transaction import TransactionalCertificate, TxnState
    runtime.finalize_count += 1
    if runtime.txn_state in {TxnState.COMMITTED, TxnState.ABORTED}:
        _contractkv_write({
            "event": "phase17_finalize_duplicate",
            "request_id": request.request_id,
            "txn_id": runtime.plan.txn_id,
            "finalize_count": runtime.finalize_count,
            "txn_state": runtime.txn_state.value,
        })
        return
    runtime.txn_state = TxnState.FINALIZING
    if runtime.verify_decision is VerifyDecision.PENDING:
        runtime.verify_decision = VerifyDecision.INCOMPLETE
    pool = scheduler.kv_cache_manager.block_pool
    blocks = scheduler.kv_cache_manager.get_blocks(request.request_id)
    physical_blocks = [block for group in blocks.blocks for block in group]
    cache_before = _contractkv_cache_entries(pool)
    num_computed = int(getattr(request, "num_computed_tokens", 0) or 0)
    commit_tokens = aligned_commit_tokens(
        runtime.plan.stable_prefix_end_token, num_computed, scheduler.block_size)
    report = runtime.verify_report
    can_commit = (
        runtime.verify_decision is VerifyDecision.PASS
        and report is not None
        and float(report.robustness_reserve) >= 0.0
        and runtime.plan.tokenization_glue_loss < scheduler.block_size
        and runtime.plan.fault_mode not in {"calibration_only", "frontend_disconnect"}
        and not getattr(runtime, "policy_errors", [])
        and not getattr(runtime, "scope_errors", [])
        and report.policy_hash == runtime.plan.policy_hash
        and report.policy_version == runtime.plan.policy_version
        and commit_tokens > 0
    )
    started = _time.perf_counter()
    certificate = None
    promotion_action = "abort"
    if can_commit:
        committed = getattr(scheduler, "_contractkv_committed_prefixes", None)
        if committed is None:
            committed = scheduler._contractkv_committed_prefixes = {}
        existing = committed.get(runtime.plan.stable_content_hash)
        if existing is None:
            scheduler.kv_cache_manager.cache_blocks(request, commit_tokens)
            scheduler._contractkv_cache_epoch = int(getattr(scheduler, "_contractkv_cache_epoch", 0)) + 1
            epoch = scheduler._contractkv_cache_epoch
            committed[runtime.plan.stable_content_hash] = {
                "commit_tokens": commit_tokens,
                "cache_epoch": epoch,
            }
            promotion_action = "register_new"
        else:
            commit_tokens = min(commit_tokens, int(existing["commit_tokens"]))
            epoch = int(existing["cache_epoch"])
            promotion_action = "join_existing"
        runtime.committed_tokens = commit_tokens
        runtime.txn_state = TxnState.COMMITTED
        certificate = TransactionalCertificate(
            txn_id=runtime.plan.txn_id,
            stable_content_hash=runtime.plan.stable_content_hash,
            layout_hash=runtime.plan.layout_hash,
            dependency_graph_hash=runtime.plan.dependency_graph_hash,
            committed_prefix_tokens=commit_tokens,
            committed_full_blocks=commit_tokens // scheduler.block_size,
            raw_margin_q05=report.raw_margin_q05,
            candidate_margin_q05=report.candidate_margin_q05,
            degradation_q95=report.degradation_q95,
            robustness_reserve=report.robustness_reserve,
            issued_cache_epoch=epoch,
            policy_hash=runtime.plan.policy_hash,
            policy_version=runtime.plan.policy_version,
            attestation_mode=runtime.plan.attestation_mode,
            model_revision=str(runtime.plan.runtime_identity.get("model_revision", "")),
            tokenizer_hash=str(runtime.plan.runtime_identity.get("tokenizer_hash", "")),
            chat_template_hash=str(runtime.plan.runtime_identity.get("chat_template_hash", "")),
            model_identity=runtime.plan.model_identity,
            task_family=runtime.plan.task_family,
            stable_prefix_hash=runtime.plan.stable_content_hash,
            scope_mode=runtime.plan.scope_mode,
            observation_identity=runtime.plan.observation_identity,
            observation_epoch=runtime.plan.observation_epoch,
            qualification_hash=runtime.plan.qualification_hash,
        )
    else:
        runtime.committed_tokens = 0
        runtime.txn_state = TxnState.ABORTED
    elapsed_ms = (_time.perf_counter() - started) * 1000.0
    cache_after = _contractkv_cache_entries(pool)
    event = {
        "event": "phase17_pstp_finalize",
        "request_id": request.request_id,
        "txn_id": runtime.plan.txn_id,
        "txn_state": runtime.txn_state.value,
        "verify_decision": runtime.verify_decision.value,
        "failure_reason": getattr(report, "failure_reason", "missing verify report"),
        "finalize_count": runtime.finalize_count,
        "stable_prefix_end_token": runtime.plan.stable_prefix_end_token,
        "num_computed_tokens": num_computed,
        "block_size": scheduler.block_size,
        "commit_tokens": runtime.committed_tokens,
        "committed_full_blocks": runtime.committed_tokens // scheduler.block_size,
        "discarded_partial_tokens": max(0, runtime.plan.stable_prefix_end_token - runtime.committed_tokens),
        "cache_entries_before": cache_before,
        "cache_entries_after": cache_after,
        "cache_entries_delta": cache_after - cache_before,
        "free_blocks_before_cleanup": pool.get_num_free_blocks(),
        "physical_block_ids": [int(block.block_id) for block in physical_blocks],
        "physical_block_ref_counts": [int(block.ref_cnt) for block in physical_blocks],
        "certificate_issued": certificate is not None,
        "promotion_action": promotion_action,
        "operation_ms": elapsed_ms,
        "fault_mode": runtime.plan.fault_mode,
        "policy_hash": runtime.plan.policy_hash,
        "policy_version": runtime.plan.policy_version,
        "attestation_mode": runtime.plan.attestation_mode,
        "policy_errors": getattr(runtime, "policy_errors", []),
        "scope_errors": getattr(runtime, "scope_errors", []),
    }
    _contractkv_write(event)
    if certificate is not None:
        cert = certificate.__dict__.copy()
        cert.update({"event": "phase17_certificate", "request_id": request.request_id})
        _contractkv_write(cert)
    import os
    if os.environ.get("CONTRACTKV_PHASE17_DOUBLE_FINALIZE") == "1":
        _contractkv_pstp_finalize(scheduler, request)


def _contractkv_phase17_post_cleanup(scheduler, request):
    runtime = getattr(request, "contractkv_pstp_runtime", None)
    if runtime is None:
        return
    pool = scheduler.kv_cache_manager.block_pool
    _contractkv_write({
        "event": "phase17_post_cleanup",
        "request_id": request.request_id,
        "txn_id": runtime.plan.txn_id,
        "txn_state": runtime.txn_state.value,
        "free_blocks_after_cleanup": pool.get_num_free_blocks(),
        "cache_entries_after_cleanup": _contractkv_cache_entries(pool),
    })
# CONTRACTKV_PHASE17_HELPER_END
'''


RECEIVE = '''            # CONTRACTKV_PHASE17_RECEIVE_BEGIN
            if stopped:
                _contractkv_phase17_receive_verify_tensors(
                    self, request, prompt_logprobs_dict.get(req_id))
            # CONTRACTKV_PHASE17_RECEIVE_END
'''

POST_CLEANUP = '''        # CONTRACTKV_PHASE17_POST_CLEANUP_BEGIN
        _contractkv_phase17_post_cleanup(self, request)
        # CONTRACTKV_PHASE17_POST_CLEANUP_END
'''


def clean_phase17(text: str) -> str:
    text = strip_region(text, HELPER_BEGIN, HELPER_END_17)
    text = strip_region(text, RECEIVE_BEGIN, RECEIVE_END)
    text = strip_region(text, POST_CLEANUP_BEGIN, POST_CLEANUP_END)
    return text


def install(text: str) -> str:
    text = clean_phase17(text)
    text = install_phase16r(text)
    anchor = HELPER_END + "\n"
    if anchor not in text:
        raise RuntimeError("Phase 16R helper anchor missing")
    text = text.replace(anchor, anchor + "\n" + HELPER + "\n", 1)
    stopped_anchor = "            if stopped:\n                kv_transfer_params = self._free_request(request)\n"
    if stopped_anchor not in text:
        raise RuntimeError("stopped request cleanup anchor missing")
    text = text.replace(stopped_anchor, RECEIVE + stopped_anchor, 1)
    free_anchor = "        self.kv_cache_manager.free(request)\n        del self.requests[request.request_id]\n"
    if free_anchor not in text:
        raise RuntimeError("native KV cleanup anchor missing")
    text = text.replace(
        free_anchor,
        "        self.kv_cache_manager.free(request)\n" + POST_CLEANUP + "        del self.requests[request.request_id]\n",
        1,
    )
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduler", type=Path, required=True)
    parser.add_argument("--action", choices=["install", "remove"], required=True)
    args = parser.parse_args()
    text = args.scheduler.read_text(encoding="utf-8")
    updated = install(text) if args.action == "install" else clean_phase17(text)
    args.scheduler.write_text(updated, encoding="utf-8")
    print(f"{args.action}: {args.scheduler}")


if __name__ == "__main__":
    main()
