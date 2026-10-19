"""Native-APC survey worker: no compiler, certification or score-based routing."""
from pathlib import Path
from collections import Counter
import argparse
import gzip
import hashlib
import json
import os
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.tsc_tableI_survey_common_v1 import tokenize_request, digest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--repeat', type=int, required=True)
    p.add_argument('--gpu', type=int, required=True)
    a = p.parse_args()
    freeze = json.loads((a.root/'freeze.json').read_text())
    receipt = json.loads((a.root/'pre_forward_receipt_v1.json').read_text())
    assert receipt['remote_commit_verified'] and receipt['freeze_sha256'] == sha(a.root/'freeze.json')
    for entry in freeze['files']:
        assert sha(ROOT/entry['path']) == entry['sha256'], entry['path']
    protocol = json.loads((ROOT/freeze['protocol_path']).read_text())
    assert int(protocol['repeat_GPU_assignment'][str(a.repeat)]) == a.gpu
    assert os.environ['CUDA_VISIBLE_DEVICES'] == str(a.gpu)
    native = json.loads((a.root/'native_preflight_v1.json').read_text())
    assert native['overlay_registered_python_files_all_match_RECORD']
    cells = a.root/'cells'/f'raw_native_r{a.repeat}'
    cells.mkdir(parents=True, exist_ok=False)
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    from transformers import AutoTokenizer
    import vllm
    from vllm import LLM, SamplingParams
    assert Path(vllm.__file__).absolute().is_relative_to(Path(native['overlay_path']).absolute())
    registry = json.loads((ROOT/'results/tsc_revision_r4/model_registry_v1.json').read_text())
    model = next(r for r in registry['models'] if r['model']=='Qwen3-8B')['model_path']
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True, trust_remote_code=False)
    start = time.time()
    llm = LLM(model=model, dtype=protocol['dtype'], trust_remote_code=False,
              max_model_len=protocol['model_window'], enable_prefix_caching=True,
              max_num_seqs=1, block_size=protocol['block_size'],
              gpu_memory_utilization=protocol['gpu_memory_utilization'],
              enforce_eager=True, max_num_batched_tokens=protocol['model_window'],
              enable_chunked_prefill=False, seed=protocol['seed'], disable_log_stats=True)
    params = SamplingParams(temperature=0, max_tokens=protocol['max_new_tokens'],
                            seed=protocol['seed'], skip_special_tokens=True)
    control = []
    probe = tokenizer.encode('Native cache accounting control. '+('cache probe token sequence '*80), add_special_tokens=False)
    llm.reset_prefix_cache()
    for index in range(2):
        r = llm.generate([{'prompt_token_ids': probe}], SamplingParams(temperature=0,max_tokens=1),use_tqdm=False)[0]
        control.append({'attempt': index, 'prompt_token_ids':probe,
                        'actual_prompt_token_ids':list(r.prompt_token_ids),
                        'native_cached_tokens': r.num_cached_tokens})
        (cells/'infrastructure_control_v1.json').write_text(json.dumps(control)+'\n')
        assert list(r.prompt_token_ids) == probe and r.num_cached_tokens is not None
    assert control[0]['native_cached_tokens']==0 and control[1]['native_cached_tokens']>0
    (cells/'infrastructure_control_v1.json').write_text(json.dumps(control)+'\n')
    sources = [json.loads(l) for l in (a.root/'inputs_v1/selected_packed_sources_v1.jsonl').open() if l.strip()]
    counts = Counter()
    resets = []
    with gzip.open(cells/'raw.jsonl.gz', 'xt', encoding='utf-8') as output:
        for source in sources:
            if source['sample'] is None:
                output.write(json.dumps({'row_type':'capacity_exclusion','source_group':source['source_group'],
                                         'family':source['family'],'status':source['status']})+'\n')
                continue
            llm.reset_prefix_cache()
            resets.append(source['source_group'])
            history = []
            for turn in range(protocol['turns_per_session']):
                row = {'row_type':'request', 'repeat':a.repeat, 'gpu':a.gpu,
                       'source_group':source['source_group'],'family':source['family'],
                       'turn':turn, 'population':'warm' if turn==0 else 'future'}
                try:
                    request = tokenize_request(tokenizer, source['sample'], history, turn, protocol)
                    ids = request['prompt_token_ids']
                    row.update({k:v for k,v in request.items() if k not in ['token_categories','wrapped_query']})
                    assert len(ids)+protocol['max_new_tokens'] <= protocol['model_window']
                    row['request_started_epoch'] = time.time()
                    began = time.perf_counter()
                    result = llm.generate([{'prompt_token_ids':ids}],params,use_tqdm=False)[0]
                    assert list(result.prompt_token_ids)==ids and result.num_cached_tokens is not None
                    hit = int(result.num_cached_tokens)
                    assert 0<=hit<len(ids) and hit%protocol['block_size']==0
                    if turn==0:
                        assert hit==0
                    generated = result.outputs[0]
                    categories = request['token_categories']
                    row.update(success=True, generation_wall_s=time.perf_counter()-began,
                        actual_prompt_token_ids_verified=True, prompt_tokens=len(ids),
                        native_cached_tokens=hit, stable_tokens=categories.count('stable'),
                        stable_cached_tokens=categories[:hit].count('stable'),
                        history_tokens=categories.count('history'), query_tokens=categories.count('query'),
                        framing_tokens=categories.count('framing'), boundary_tokens=request['boundary_tokens'],
                        output_token_ids=list(generated.token_ids),output_ids_sha256=digest(list(generated.token_ids)),
                        output_text=generated.text,finish_reason=generated.finish_reason,
                        stop_reason=generated.stop_reason, request_id=result.request_id)
                    assert row['stable_tokens']+row['history_tokens']+row['query_tokens']+row['framing_tokens']==len(ids)
                    history.append({'query':request['wrapped_query'],'answer':generated.text})
                    counts['completed']+=1
                    counts[source['family']]+=1
                except Exception as error:
                    row.update(success=False,error_type=type(error).__name__,error=str(error))
                    output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush()
                    (cells/'failure.txt').write_text(traceback.format_exc())
                    raise
                output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush()
                if counts['completed']%10==0:
                    progress={'repeat':a.repeat,'completed':counts['completed'],'last_family':source['family'],
                              'last_source':source['source_group'],'epoch_time':time.time()}
                    (cells/'progress.json').write_text(json.dumps(progress)+'\n')
                    print(json.dumps(progress),flush=True)
    assert counts['completed']==len(resets)*protocol['turns_per_session']
    record={'repeat':a.repeat,'gpu':a.gpu,'native_vllm_path':vllm.__file__,
            'completed_requests':counts['completed'],'completed_by_family':dict(counts),
            'session_cache_resets':resets,'wall_s':time.time()-start,
            'raw_sha256':sha(cells/'raw.jsonl.gz'),'freeze_sha256':sha(a.root/'freeze.json'),
            'execution_complete':True,'generation_scores_used_for_selection':False}
    (cells/'completion_v1.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'repeat':a.repeat,'complete':True,'requests':counts['completed']}),flush=True)


if __name__=='__main__':
    main()
