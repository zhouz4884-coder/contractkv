"""Create an independent backend with pointwise gates before KV commit."""
import argparse
from datetime import datetime,timezone
import difflib
import hashlib
import json
from pathlib import Path
import py_compile
import shutil


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text,old,new):
    if text.count(old)!=1: raise ValueError('Backend anchor is not unique: '+old[:90])
    return text.replace(old,new,1)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args(); root=a.root.resolve()
    source=root/'third_party/vllm-contractkv-tsc-r1r-slice'; target=root/'third_party/vllm-contractkv-tsc-r2-margin'
    commitment=json.loads((root/'configs/tsc_revision_r1r_backend_commitment_v2.json').read_text(encoding='utf-8'))
    for item in commitment['source_files']:
        if sha(source/item['file'])!=item['after_sha256']: raise ValueError('Original backend changed')
    if target.exists(): raise RuntimeError('Preserve existing backend/partial attempt')
    changes={}
    name='vllm/v1/engine/__init__.py'; text=(source/name).read_text(encoding='utf-8')
    text=replace_once(text,'    cached_prefix_read_tokens: int = 0\n',
        '    cached_prefix_read_tokens: int = 0\n'
        '    raw_margin_min: float = float("nan")\n'
        '    candidate_margin_min: float = float("nan")\n'
        '    raw_margin_min_index: int = -1\n'
        '    candidate_margin_min_index: int = -1\n'
        '    minimum_margin_guard_passed: bool = False\n')
    changes[name]=text
    name='vllm/v1/core/sched/scheduler.py'; text=(source/name).read_text(encoding='utf-8')
    text=replace_once(text,'\nimport os\n','\nimport os\nfrom scripts.tsc_revision_r2_margin_policy import minimum_margin_gate\nfrom scripts.tsc_revision_r2_execution_trace import emit_trace\n')
    text=replace_once(text,'        certificate_hash = ""\n\n        try:\n',
        '        certificate_hash = ""\n'
        '        raw_min = candidate_min = float("nan")\n'
        '        raw_min_index = candidate_min_index = -1\n'
        '        minimum_margin_passed = False\n\n        try:\n')
    anchor='            if (all(rank == 1 for rank in candidate_ranks) and stop_ok\n'
    block='''            margin_result = minimum_margin_gate(
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
'''
    text=replace_once(text,anchor,block+anchor)
    text=replace_once(text,'                    and terminal_stop_margin >= min_stop_margin):',
        '                    and terminal_stop_margin >= min_stop_margin\n                    and minimum_margin_passed):')
    text=replace_once(text,'                failure = "token_path_or_margin_guard_failed"',
        '                failure = ("pointwise_margin_guard:" + margin_result["reason"]\n'
        '                           if not minimum_margin_passed else "token_path_or_margin_guard_failed")')
    text=replace_once(text,'            cached_prefix_read_tokens=int(getattr(request, "contractkv_cached_prefix_read_tokens", 0)),',
        '            cached_prefix_read_tokens=int(getattr(request, "contractkv_cached_prefix_read_tokens", 0)),\n'
        '            raw_margin_min=raw_min, candidate_margin_min=candidate_min,\n'
        '            raw_margin_min_index=raw_min_index, candidate_margin_min_index=candidate_min_index,\n'
        '            minimum_margin_guard_passed=minimum_margin_passed,')
    changes[name]=text
    name='vllm/entrypoints/openai/api_server.py'; text=(source/name).read_text(encoding='utf-8')
    text=replace_once(text,'        "raw_margin_q05": (result.raw_margin_q05',
        '        "raw_margin_min": result.raw_margin_min if math.isfinite(result.raw_margin_min) else None,\n'
        '        "candidate_margin_min": result.candidate_margin_min if math.isfinite(result.candidate_margin_min) else None,\n'
        '        "raw_margin_min_index": result.raw_margin_min_index,\n'
        '        "candidate_margin_min_index": result.candidate_margin_min_index,\n'
        '        "minimum_margin_guard_passed": result.minimum_margin_guard_passed,\n'
        '        "raw_margin_q05": (result.raw_margin_q05')
    changes[name]=text
    name='vllm/v1/worker/gpu_model_runner.py'; text=(source/name).read_text(encoding='utf-8')
    text=replace_once(text,'\nimport gc\n','\nimport gc\nimport os\nfrom scripts.tsc_revision_r2_execution_trace import emit_trace\n')
    anchor='        output = ModelRunnerOutput(\n'
    block='''        if os.environ.get("CONTRACTKV_R2_EXECUTION_TRACE"):
            emit_trace("CONTRACTKV_R2_EXECUTION_TRACE", {
                "event": "r2_actual_model_runner_execution",
                "device": str(self.device),
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "request_ids": list(req_ids_output_copy),
                "scheduled_tokens": {key: int(value) for key, value in scheduler_output.num_scheduled_tokens.items()},
                "active_input_requests": int(self.input_batch.num_reqs),
                "scheduled_token_count": int(num_scheduled_tokens),
                "padded_input_token_count": int(num_input_tokens),
                "cudagraph_mode": str(cudagraph_runtime_mode),
                "input_ids_shape": list(getattr(input_ids, "shape", ())),
                "hidden_states_shape": list(getattr(hidden_states, "shape", ())),
                "sampling_hidden_states_shape": list(getattr(locals().get("sample_hidden_states"), "shape", ())),
                "sampling_logits_shape": list(getattr(logits, "shape", ())),
                "sampled_token_ids": valid_sampled_token_ids,
                "prompt_logprob_shapes": {key: list(getattr(getattr(value, "logprobs", None), "shape", ())) for key, value in prompt_logprobs_dict.items()}})
'''
    text=replace_once(text,anchor,block+anchor); changes[name]=text
    for name,text in changes.items(): compile(text,name,'exec')
    shutil.copytree(source,target,symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
    entries=[]; patch=[]
    for name,text in changes.items():
        before=(source/name).read_text(encoding='utf-8')
        (target/name).write_text(text,encoding='utf-8',newline='\n')
        py_compile.compile(str(target/name),doraise=True)
        entries.append({'file':name,'before_sha256':sha(source/name),'after_sha256':sha(target/name)})
        patch.extend(difflib.unified_diff(before.splitlines(keepends=True),text.splitlines(keepends=True),fromfile='a/'+name,tofile='b/'+name))
    for item in commitment['source_files']:
        if sha(source/item['file'])!=item['after_sha256']: raise ValueError('Original backend was modified')
    patch_path=root/'third_party/patches/contractkv_r2_pointwise_margin_v1.patch'
    if patch_path.exists(): raise RuntimeError('Preserve existing patch')
    patch_path.write_text(''.join(patch),encoding='utf-8',newline='\n')
    record={'schema_version':'tsc-r2.pointwise-margin-backend.v1','timestamp':datetime.now(timezone.utc).isoformat(),
            'base':'vllm-contractkv-tsc-r1r-slice','new_backend':target.name,'original_six_source_files_unchanged':True,
            'source_files':entries,'patch_sha256':sha(patch_path),
            'project_dependencies':[{'path':name,'sha256':sha(root/name)} for name in ('scripts/tsc_revision_r2_margin_policy.py','scripts/tsc_revision_r2_execution_trace.py')],
            'no_model_weights_or_attention_kernel_changes':True,'new_margin_floors_default_disabled':True,
            'trace_is_opt_in_model_runner_metadata_not_per_kernel_profiler':True}
    out=root/'configs/tsc_revision_r2_backend_commitment_v1.json'
    with out.open('x',encoding='utf-8') as stream: stream.write(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))


if __name__=='__main__': main()
