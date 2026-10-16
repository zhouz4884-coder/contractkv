"""Separate actual witness length from emitted positions beyond that length."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write,first_divergence
from scripts.tsc_revision_r1r_witness_decisions import indexed


def horizon_measures(reference_count,future_ids,witness_ids=None):
    if reference_count<=0: raise ValueError('Missing positive witness length')
    if witness_ids is not None and len(witness_ids)!=reference_count: raise ValueError('Witness count disagrees with IDs')
    divergence=first_divergence(witness_ids,future_ids) if witness_ids is not None else 'unavailable'
    return {'reference_returned_tokens':reference_count,'future_returned_tokens':len(future_ids),
            'positions_beyond_reference_length':max(0,len(future_ids)-reference_count),
            'witness_ids_available':witness_ids is not None,'first_divergence_from_witness':divergence,
            'future_positions_from_first_divergence':max(0,len(future_ids)-divergence) if isinstance(divergence,int) and divergence>=0 else (0 if divergence==-1 else 'unavailable')}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--root',type=Path)
    parser.add_argument('--legacy-only',action='store_true')
    parser.add_argument('--legacy-root',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); pairs=[]; current_cells=0; legacy_cells=0
    if not args.legacy_only and args.root is None: parser.error('--root is required unless --legacy-only')
    current_paths=[] if args.legacy_only else sorted((args.root/'cells').glob('*/summary.json'))
    for path in current_paths:
        declaration=json.loads(path.read_text()); raw=path.parent/'raw.jsonl'
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=declaration['raw_file_sha256']: raise ValueError('Current raw hash mismatch')
        rows=read(path.parent/'raw.jsonl'); current_cells+=1
        first=next(r for r in rows if r['row_type']=='future')
        if first['policy']=='raw-order': continue
        witnesses=indexed(rows)
        for row in rows:
            if row['row_type']!='future' or row['effective_level']=='L0': continue
            key=(row['certificate_namespace'],row['query_scope'])
            if key not in witnesses: raise ValueError('Compiled future has no recorded witness')
            verification,witness=witnesses[key]
            if not verification['certificate_issued'] or verification['selected_level']!=row['effective_level'] or witness['finish_reason']!='stop':
                raise ValueError('Compiled future and witness admission disagree')
            pairs.append({'cohort':'R1R','study':row['study'],'model':row['model'],'policy':row['policy'],'budget_condition':'native',
                          'repeat':row['repeat'],'source_group':row['source_group'],'family':row['family'],'session_id':row['session_id'],
                          'turn_id':row['turn_id'],'output_budget':row['output_budget'],'witness_session_id':witness['session_id'],
                          'witness_turn_id':witness['turn_id'],**horizon_measures(len(witness['output_token_ids']),row['output_token_ids'],witness['output_token_ids'])})
    for path in sorted((args.legacy_root/'cells').glob('*/summary.json')):
        declaration=json.loads(path.read_text()); raw=path.parent/'raw.jsonl'
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=declaration['source_sha256']: raise ValueError('Legacy raw hash mismatch')
        rows=read(path.parent/'raw.jsonl'); first=next(r for r in rows if r['row_type']=='future')
        if first['policy']!='contractkv': continue
        legacy_cells+=1; witnesses={r['session_id']:r for r in rows if r['row_type']=='canary'}
        study=path.parent.name.split('_')[0]; condition=path.parent.name.rsplit('_',1)[1]
        for row in rows:
            if row['row_type']!='future' or row['effective_level']=='L0': continue
            witness=witnesses[row['session_id']]
            if not witness['certificate_issued'] or witness.get('raw_finish_reason')!='stop': raise ValueError('Invalid legacy reference admission')
            ids=witness.get('reference_output_token_ids')
            pairs.append({'cohort':'R1','study':study,'model':row['model'],'policy':row['policy'],'budget_condition':condition,
                          'repeat':row['repeat'],'source_group':row['source_group'],'family':row['family'],'session_id':row['session_id'],
                          'turn_id':row['turn_id'],'output_budget':row['output_budget'],'witness_session_id':row['session_id'],
                          'witness_turn_id':0,**horizon_measures(int(witness['reference_output_tokens']),row['output_token_ids'],ids if ids else None)})
    groups=defaultdict(list)
    for row in pairs: groups[tuple(row[k] for k in ('cohort','study','model','policy','budget_condition'))].append(row)
    summary=[]
    for key,rows in sorted(groups.items()):
        summary.append(dict(zip(('cohort','study','model','policy','budget_condition'),key))|{
            'compiled_futures':len(rows),'reference_tokens_min':min(r['reference_returned_tokens'] for r in rows),
            'reference_tokens_max':max(r['reference_returned_tokens'] for r in rows),
            'future_tokens_max':max(r['future_returned_tokens'] for r in rows),
            'outputs_exceed_reference_length':sum(r['positions_beyond_reference_length']>0 for r in rows),
            'positions_beyond_reference_length':sum(r['positions_beyond_reference_length'] for r in rows),
            'maximum_extra_positions':max(r['positions_beyond_reference_length'] for r in rows),
            'comparable_witness_sequences':sum(r['witness_ids_available'] for r in rows),
            'divergences_from_witness':sum(r['witness_ids_available'] and r['first_divergence_from_witness']!=-1 for r in rows) if any(r['witness_ids_available'] for r in rows) else 'unavailable'})
    args.output.mkdir(parents=True,exist_ok=True)
    if pairs: write(args.output/'output_horizon_pairs_v1.csv',pairs); write(args.output/'output_horizon_summary_v1.csv',summary)
    audit={'schema_version':'tsc-r1r.output-horizon-audit.v1','current_cohort_requested':not args.legacy_only,
           'current_complete_cell_files':current_cells,'legacy_policy_cells':legacy_cells,
           'new_compiled_futures':sum(r['cohort']=='R1R' for r in pairs),'legacy_compiled_futures':sum(r['cohort']=='R1' for r in pairs),
           'new_witness_sequences_available':sum(r['cohort']=='R1R' and r['witness_ids_available'] for r in pairs),
           'scope':'Returned token counts include the terminal stop when returned. Divergence indices are zero-based. Positional excess is reported separately; it is never treated as certified behavior. Any path divergence also breaks subsequent teacher-forced-path interpretation.',
           'legacy_sequence_logging_limit':'Original R1 main references retain length/hash but not direct IDs. Sequence comparisons are unavailable where IDs were not archived.',
           'fallbacks':'This horizon table describes compiled routes only; raw and fallback denominators remain in quality/performance tables.'}
    (args.output/'output_horizon_audit_v1.json').write_text(json.dumps(audit,indent=2)+'\n'); print(json.dumps(audit))


if __name__=='__main__': main()
