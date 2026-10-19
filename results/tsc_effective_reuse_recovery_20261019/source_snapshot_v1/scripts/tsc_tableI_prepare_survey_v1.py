"""Freeze sources and task-faithful context without labels or model outcomes."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
import argparse
import hashlib
import json
import os
import sys

os.environ.update(USE_TORCH='0', USE_TF='0', HF_HUB_OFFLINE='1',
                  TRANSFORMERS_OFFLINE='1', CUDA_VISIBLE_DEVICES='')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from transformers import AutoTokenizer
from scripts.tsc_revision_build_inputs import source, family
from scripts.tsc_revision_r4_input_fidelity import pack_task_input
from scripts.tsc_tableI_survey_common_v1 import messages_for, digest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return [json.loads(l) for l in Path(path).open(encoding='utf-8') if l.strip()]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--tokenizer', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    protocol = json.loads(a.protocol.read_text())
    ex = ROOT/'results/tsc_revision_r4/fidelity_complete_exclusion_audit_v1.json'
    excluded = set(json.loads(ex.read_text())['excluded_source_groups'])
    exclusion_files = [{'path': ex.relative_to(ROOT).as_posix(), 'sha256': sha(ex)}]
    extra = sorted((ROOT/'results/tsc_revision_r4').glob('**/*selected_sessions*.jsonl'))
    extra += [ROOT/'results/tsc_revision_evidence_closure_20261017/tableI_service_candidate/g1_sessions.jsonl']
    for path in extra:
        if not path.exists():
            continue
        rr = read(path)
        excluded.update(source(r) for r in rr)
        exclusion_files.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)})
    pool_path = ROOT/protocol['source_pool']
    candidates = {}
    for row in read(pool_path):
        if source(row) not in excluded:
            candidates.setdefault(source(row), row)
    ordered = sorted(candidates, key=lambda s: hashlib.sha256((str(protocol['seed'])+':'+s).encode()).hexdigest())
    selected = []
    for fam in protocol['families']:
        group = [candidates[s] for s in ordered if family(candidates[s]) == fam][:protocol['sources_per_family']]
        assert len(group) == protocol['sources_per_family'], fam
        selected += group
    tokenizer = AutoTokenizer.from_pretrained(a.tokenizer, local_files_only=True, trust_remote_code=False)
    results = []
    for index, row in enumerate(selected):
        # Deliberately discard answer/label and old token counters before packing.
        sample = {'family': family(row), 'source_group': source(row),
                  'source_dataset': row['dataset'], 'source_task': row['task'],
                  'sample_id': str(row['sample_id']),
                  'segments': [{'type': s['type'], 'text': s['text']} for s in row['segments']]}
        assert all(s['type'] not in {'CHAT_HISTORY','TOOL_OBS','SCRATCHPAD'} for s in sample['segments'])
        query = '\n'.join(s['text'] for s in sample['segments'] if s['type']=='USER_QUERY')
        assert query
        question_tokens = max(len(tokenizer.encode(w.format(query=query), add_special_tokens=False))
                              for w in protocol['query_wrappers'])
        reserve = (protocol['turns_per_session']-1)*(question_tokens+protocol['max_new_tokens']+32)+256

        def fit(candidate):
            maximum = max(len(tokenizer.apply_chat_template(messages_for(candidate, [], t, protocol)[0],
                tokenize=True, add_generation_prompt=True, enable_thinking=False)) for t in range(10))
            return {'fits': maximum+reserve+protocol['max_new_tokens'] <= protocol['model_window'],
                    'largest_current_request_tokens': maximum, 'history_reserved_tokens': reserve,
                    'prompt_history_and_output_bound': maximum+reserve+protocol['max_new_tokens']}

        prepared = pack_task_input(sample, fit)
        item = {'selection_index': index, 'source_group': sample['source_group'],
                'family': sample['family'], 'source_segments_sha256': digest(sample['segments']),
                'status': prepared['status'], 'history_reserved_tokens': reserve,
                'packing_audit': {k:v for k,v in prepared.items() if k!='sample'},
                'sample': prepared['sample']}
        if prepared['sample'] is None:
            item['unpacked_sample'] = sample
        results.append(item)
        print(json.dumps({'prepared_source': index+1, 'family': sample['family'],
                          'status': item['status']}), flush=True)
    a.output.mkdir(parents=True)
    out = a.output/'selected_packed_sources_v1.jsonl'
    out.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n' for r in results), encoding='utf-8')
    report = {'protocol_sha256': sha(a.protocol), 'source_pool_sha256': sha(pool_path),
              'excluded_source_groups': sorted(excluded), 'exclusion_files': exclusion_files,
              'source_selection_before_capacity_checks': True, 'no_source_replacement': True,
              'selected_sources': len(results), 'distinct_sources': len({r['source_group'] for r in results}),
              'selected_by_family': dict(Counter(r['family'] for r in results)),
              'status_counts': dict(Counter(r['status'] for r in results)),
              'eligible_sources': sum(r['sample'] is not None for r in results),
              'selected_packed_file_sha256': sha(out), 'new_model_forwards': 0,
              'selection_and_packing_read_fields': ['source identity', 'dataset/task', 'segment type/text', 'tokenizer window'],
              'label_and_model_outcome_access_in_selection_or_packing': False}
    (a.output/'input_preparation_v1.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['excluded_source_groups','exclusion_files']}), flush=True)


if __name__ == '__main__':
    main()
