"""Patch only a dedicated runtime copy; save exact before/after commitments."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def patch(runtime):
    changed = []
    def edit(name, replacements):
        p = runtime / name
        assert not p.is_symlink() and p.resolve().is_relative_to(runtime.resolve())
        old = p.read_text()
        new = old
        for a, b in replacements:
            assert new.count(a) == 1, (name, a[:90], new.count(a))
            new = new.replace(a, b)
        ast.parse(new)
        p.write_text(new)
        changed.append(dict(path=name, before_sha256=hashlib.sha256(old.encode()).hexdigest(),
                            after_sha256=hashlib.sha256(new.encode()).hexdigest()))
    edit("vllm/v1/engine/async_llm.py", [
        ('        params = SamplingParams(\n            temperature=0,\n            top_p=1,\n            max_tokens=1,\n            prompt_logprobs=2,\n            extra_args={"contractkv_witness_logprob_start": verify_spec.verify_start_token - 1},\n        )',
         '        from scripts.tsc_exploratory_native_v2 import MODE\n'
         '        if verify_spec.attestation_mode == MODE:\n'
         '            assert prompt_token_ids[verify_spec.verify_start_token:] == list(verify_spec.reference_answer_ids) + [verify_spec.terminal_stop_token_id]\n'
         '            prompt_token_ids = prompt_token_ids[:verify_spec.verify_start_token]\n'
         '            params = SamplingParams(temperature=0, top_p=1, seed=14014, max_tokens=128, logprobs=2)\n'
         '        else:\n'
         '            params = SamplingParams(temperature=0, top_p=1, max_tokens=1, prompt_logprobs=2,\n'
         '                extra_args={"contractkv_witness_logprob_start": verify_spec.verify_start_token - 1})')])
    edit("vllm/v1/engine/__init__.py", [
        ('    minimum_margin_guard_passed: bool = False',
         '    minimum_margin_guard_passed: bool = False\n    fused_prompt_ids: list[int] | None = None\n    fused_output_ids: list[int] | None = None\n    fused_finish: str | None = None')])
    edit("vllm/entrypoints/openai/api_server.py", [
        ('        "request_id": payload.request_id,\n        "txn_id": result.txn_id,',
         '        "request_id": payload.request_id,\n        "fused_prompt_ids": result.fused_prompt_ids,\n        "fused_output_ids": result.fused_output_ids,\n        "fused_finish": result.fused_finish,\n        "txn_id": result.txn_id,')])
    edit("vllm/v1/core/sched/scheduler.py", [
        ('        # Source-level compact verification owns its finalization path.\n        return',
         '        # Source-level compact verification owns its finalization path.\n'
         '        from scripts.tsc_exploratory_native_v2 import audit_native_release\n'
         '        audit_native_release(scheduler, request)\n        return'),
        ('            # Check for stop and update request status.\n',
         '            from scripts.tsc_exploratory_native_v2 import collect\n'
         '            collect(request, new_token_ids, logprobs, req_index)\n'
         '            # Check for stop and update request status.\n'),
        ('            if stopped:\n                kv_transfer_params = self._free_request(request)',
         '            if stopped:\n                from scripts.tsc_exploratory_native_v2 import generic_before_free\n'
         '                generic_before_free(self, request)\n                kv_transfer_params = self._free_request(request)'),
        ('            if prompt_logprobs_tensors is None:\n                raise ValueError("prompt_logprobs_missing")',
         '            from scripts.tsc_exploratory_native_v2 import is_fused, fused_rows\n'
         '            if is_fused(request):\n                prompt_logprobs_tensors = fused_rows(request)\n'
         '            if prompt_logprobs_tensors is None:\n                raise ValueError("prompt_logprobs_missing")'),
        ('                    self.kv_cache_manager.cache_blocks(\n                        request, committed_tokens)',
         '                    self.kv_cache_manager.cache_blocks(\n                        request, committed_tokens)\n'
         '                    from scripts.tsc_exploratory_native_v2 import mark\n'
         '                    mark(self, request, committed_tokens, True)'),
        ('            minimum_margin_guard_passed=minimum_margin_passed,\n',
         '            minimum_margin_guard_passed=minimum_margin_passed,\n'
         '            **__import__("scripts.tsc_exploratory_native_v2", fromlist=["actual_fields"]).actual_fields(request),\n')])
    edit("vllm/v1/core/block_pool.py", [
        ('        ret: list[KVCacheBlock] = self.free_block_queue.popleft_n(num_blocks)',
         '        from scripts.tsc_exploratory_native_v2 import allocate\n'
         '        ret: list[KVCacheBlock] = allocate(self, num_blocks)')])
    return changed


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args()
    assert "tsc_exploratory_mechanisms_20261020" in str(a.runtime.resolve())
    assert not a.receipt.exists()
    a.receipt.write_text(json.dumps(dict(status="PATCHED_CPU_PARSE_PASS", changed=patch(a.runtime)), indent=2)+"\n")
