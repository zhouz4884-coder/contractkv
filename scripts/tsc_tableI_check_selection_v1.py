"""Independent rank/protected-field audit against the sealed candidate pool."""
from pathlib import Path
from collections import Counter
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def identity(row):
    return row['dataset']+':'+row['task']+':'+str(row['metadata']['source_group_id'])


def family(row):
    if row['dataset'] in {'RULER','RepoBench'}:return row['dataset']
    return {'hotpotqa':'HotpotQA','narrativeqa':'NarrativeQA','qasper':'Qasper'}[row['task']]


def main():
    study=ROOT/'results/tsc_tableI_remeasurement_20261018'
    protocol=json.loads((ROOT/'configs/tsc_tableI_remeasurement_20261018_v1.json').read_text())
    prep=json.loads((study/'inputs_v1/input_preparation_v1.json').read_text())
    pool=ROOT/protocol['source_pool']
    assert hashlib.sha256(pool.read_bytes()).hexdigest()==prep['source_pool_sha256']
    rows=[json.loads(l) for l in pool.open(encoding='utf-8') if l.strip()]
    excluded=set(prep['excluded_source_groups']);unique={}
    for row in rows:
        if identity(row) not in excluded:unique.setdefault(identity(row),row)
    ordered=sorted(unique,key=lambda s:hashlib.sha256((str(protocol['seed'])+':'+s).encode()).hexdigest())
    expected=[]
    for fam in protocol['families']:
        expected += [s for s in ordered if family(unique[s])==fam][:25]
    selected=[json.loads(l) for l in (study/'inputs_v1/selected_packed_sources_v1.jsonl').open(encoding='utf-8') if l.strip()]
    assert [r['source_group'] for r in selected]==expected
    optional={'RAG_CHUNK','DOC_CONTEXT','SYNTHETIC_CONTEXT','REPO_CONTEXT','REPO_IMPORT','REPO_CLASS','REPO_FUNCTION'}
    full=0;cropped=0
    for selected_row in selected:
        original=unique[selected_row['source_group']]
        stripped=[{'type':s['type'],'text':s['text']} for s in original['segments']]
        assert digest(stripped)==selected_row['source_segments_sha256']
        if selected_row['sample'] is None:continue
        packed=selected_row['sample']['segments']
        assert [s['type'] for s in packed]==[s['type'] for s in stripped]
        for before,after in zip(stripped,packed):
            if before['type'] not in optional:assert before['text']==after['text']
        for ledger in selected_row['packing_audit']['segment_ledger']:
            i=ledger['segment_index'];text=stripped[i]['text'];kept=ledger['kept_original_character_ranges']
            if ledger['omitted_original_character_range'] is None:
                assert packed[i]['text']==text
            else:
                marker='\n# CONTEXT_OMITTED_BY_WINDOW_BUDGET\n' if stripped[i]['type'].startswith('REPO_') else '\n\n[CONTEXT_OMITTED_BY_WINDOW_BUDGET]\n\n'
                head=text[kept[0][0]:kept[0][1]] if kept and kept[0][0]==0 else ''
                tail=text[kept[-1][0]:kept[-1][1]] if kept and kept[-1][1]==len(text) and kept[-1][0]>0 else ''
                assert packed[i]['text']==head+marker+tail
        if stripped==packed:full+=1
        else:cropped+=1
    report={'status':'PASS','selected_sources':len(selected),
            'all_selected_sources_equal_fixed_hash_order_without_replacement':True,
            'all_source_segment_hashes_match_candidate_pool':True,
            'all_protected_question_system_and_CODE_PREFIX_texts_unchanged':True,
            'all_optional_context_crops_exact_original_substrings_with_declared_marker':True,
            'full_original_inputs':full,'optional_context_cropped_inputs':cropped,
            'selected_by_family':dict(Counter(r['family'] for r in selected)),
            'reference_answers_or_model_outputs_used_to_select_sources':False,
            'new_model_requests':0,'GPU_execution_completion_claim':False}
    output=study/'input_independent_integrity_v1.json';assert not output.exists()
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
