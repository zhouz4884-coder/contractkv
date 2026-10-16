"""Post-output evidence availability and absolute utility, without test selection."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase20a_official_quality import references


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):return [json.loads(line) for line in Path(path).open(encoding='utf-8') if line.strip()]


def normalize(text):return ' '.join(str(text).casefold().split())


def context(sample):
    return '\n'.join(row['text'] for row in sample['segments'] if row['type'] not in {'SYS_PROMPT','USER_QUERY','TOOL_OBS','CHAT_HISTORY','SCRATCHPAD'})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--original-input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert not args.output.exists()
    assert json.loads((args.root/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))['execution_complete']
    freeze=json.loads((args.root/'freeze.json').read_text(encoding='utf-8'));config=freeze['protocol']
    assert len(config['input_files'])==1
    packed_path=args.root/'source_snapshot'/next(iter(config['input_files'].values()))
    packed={row['revision_source_group']:row for row in read(packed_path)}
    original={row['revision_source_group']:row for row in read(args.original_input)}
    assert set(packed)==set(original)
    metadata={}
    for identity,sample in packed.items():
        answers=references(sample.get('answer',''));old=context(original[identity]);new=context(sample)
        old_flags=[bool(normalize(answer)) and normalize(answer) in normalize(old) for answer in answers]
        new_flags=[bool(normalize(answer)) and normalize(answer) in normalize(new) for answer in answers]
        metadata[identity]={'source_group':identity,'family':sample['revision_family'],
            'input_status':sample['revision_input_fidelity']['status'],
            'any_reference_literal_in_original_context':any(old_flags),
            'any_reference_literal_in_packed_context':any(new_flags),
            'literal_lost_by_optional_packing':any(old_flags) and not any(new_flags),
            'reference_literals_sha256':hashlib.sha256(json.dumps(answers,ensure_ascii=False).encode()).hexdigest(),
            'original_context_characters':len(old),'packed_context_characters':len(new)}
    pairs_path=args.root/'all_business_quality_v1.csv'
    with pairs_path.open(encoding='utf-8',newline='') as stream:pairs=list(csv.DictReader(stream))
    groups=defaultdict(list)
    for row in pairs:
        for population in ('all_business',row['row_type']):groups[row['model'],row['policy'],row['source_group'],population].append(row)
    source_results=[]
    for (model,policy,identity,population),rows in sorted(groups.items()):
        compiled=[row for row in rows if row['effective_level']!='L0']
        raw_scores=[float(row['raw_score']) for row in rows];policy_scores=[float(row['policy_score']) for row in rows]
        source_results.append({**metadata[identity],'model':model,'policy':policy,'population':population,
            'paired_answers':len(rows),'raw_mean_frozen_score':mean(raw_scores),'policy_mean_frozen_score':mean(policy_scores),
            'raw_positive_score_answers':sum(value>0 for value in raw_scores),
            'raw_unit_score_answers':sum(value==1 for value in raw_scores),
            'compiled_answers':len(compiled),
            'compiled_raw_mean_frozen_score':mean(float(row['raw_score']) for row in compiled) if compiled else None,
            'compiled_positive_frozen_score_answers':sum(float(row['policy_score'])>0 for row in compiled),
            'compiled_unit_frozen_score_answers':sum(float(row['policy_score'])==1 for row in compiled),
            'all_route_material_drops':sum(float(row['quality_drop'])>.03 for row in rows),
            'all_route_material_improvements':sum(float(row['quality_drop'])<-.03 for row in rows)})
    routing=json.loads((args.root/'routing_attribution_v1.json').read_text(encoding='utf-8'))
    route_groups=defaultdict(Counter)
    for cell in routing['cells']:
        for row in cell['request_records']:
            route_groups[cell['model'],cell['policy'],row['source_group']][row['terminal_routing_cause']]+=1
    result={'schema_version':'tsc-r4.post-output-fidelity-utility-audit.v1','source_sha256':sha(__file__),
        'freeze_sha256':sha(args.root/'freeze.json'),'original_input_sha256':sha(args.original_input),
        'packed_input_sha256':sha(packed_path),'paired_business_csv_sha256':sha(pairs_path),
        'source_metadata':list(metadata.values()),'source_model_population_results':source_results,
        'all_business_terminal_routes':[{'model':key[0],'policy':key[1],'source_group':key[2],'counts':dict(value)} for key,value in sorted(route_groups.items())],
        'new_GPU_requests':0,'reference_labels_used_only_after_generation':True,
        'test_sources_or_scores_not_filtered_or_replaced':True,
        'limits':['Literal presence is not semantic answerability, and absence is not proof of impossibility.',
                  'RepoBench next-line reference may be absent from the prefix by task design; do not call that input damage.',
                  'Positive frozen score is partial metric credit, not a binary correctness guarantee.',
                  'Compiled subset quality is selected by qualification; compare paired behavior and report absolute utility separately.']}
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'sources':len(metadata),'source_model_population_rows':len(source_results),'new_GPU_requests':0}))


if __name__=='__main__':main()
