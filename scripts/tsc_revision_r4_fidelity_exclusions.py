"""Verify all known-source exclusions before any fidelity test selection.

This never opens the candidate pool or selects new test sources.
"""
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_build_inputs import source, read


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def main():
    output = Path('results/tsc_revision_r4/fidelity_complete_exclusion_audit_v1.json')
    if output.exists():
        raise ValueError('Preserve source exclusion audits')
    parent = Path('results/tsc_revision_r4/inputs/input_commitment_v1.json')
    commitment = json.loads(parent.read_text(encoding='utf-8'))
    provenance = Path('results/tsc_revision_r4/historical_input_additional_provenance_v1.json')
    aliases = {r['original_logical_path']: r['recovered_path'] for r in json.loads(provenance.read_text())['records']}
    aliases['results/cross_model/llama_broad_generalization_r3/development_sessions_v0.jsonl'] = (
        'results/tsc_revision_r4/historical_input_snapshots_v1/original_llama_development.jsonl')
    excluded = set()
    files = []
    for record in commitment['exclusion_files']:
        path = Path(record['file'])
        if not path.exists():
            path = Path(aliases.get(record['file'], record['file']))
        if sha(path) != record['sha256']:
            raise ValueError('Previously committed input changed: ' + str(path))
        rows = read(path)
        excluded.update(source(row) for row in rows)
        files.append({'logical_path': record['file'], 'resolved_path': path.as_posix(),
                      'sha256': sha(path), 'rows': len(rows)})
    if len(excluded) != 462:
        raise ValueError('Preserve the original pre-R4 exclusion boundary')
    r4_path = Path('results/tsc_revision_r4/inputs/heldout_sealed_sessions_v1.jsonl')
    if sha(r4_path) != commitment['cohorts'][r4_path.name]['sha256']:
        raise ValueError('Original R4 source pool changed')
    r4 = {source(row) for row in read(r4_path)}
    if len(r4) != 50 or r4 & excluded:
        raise ValueError('Original R4 disjointness failed')
    excluded.update(r4)
    additional_path = Path('results/tsc_revision_r4/fidelity_additional_service_exclusion_proof_v1.json')
    additional = json.loads(additional_path.read_text(encoding='utf-8'))
    additional_counts = {}
    for kind, commitment_path in [('marker', 'results/tsc_service/tsc_service_trace_commitment_v0.json'),
                                   ('task_quality', 'results/tsc_service/tsc_service_quality_trace_commitment_v0.json')]:
        item = additional[kind]
        path = Path(item['path'])
        rows = read(path)
        original = json.loads(Path(commitment_path).read_text(encoding='utf-8'))
        if sha(path) != item['raw_sha256'] or canonical(rows) != original['sessions_sha256']:
            raise ValueError('Original service input canonical commitment mismatch')
        groups = {source(row) for row in rows}
        if sorted(groups) != item['source_groups']:
            raise ValueError('Service source identities changed')
        additional_counts[kind] = {'rows': len(rows), 'source_groups': len(groups),
                                  'newly_added_beyond_preceding_sets': len(groups-excluded)}
        excluded.update(groups)
    result = {'schema_version': 'tsc-r4.task-fidelity-exclusion-audit.v1',
              'analysis_source_sha256': sha(Path(__file__)), 'pre_R4_sources': 462, 'R4_new_sources': 50,
              'union_with_R4': 512, 'additional_service_sources': additional_counts,
              'total_excluded_unique_sources': len(excluded), 'excluded_source_groups': sorted(excluded),
              'excluded_set_sha256': hashlib.sha256(json.dumps(sorted(excluded)).encode()).hexdigest(),
              'original_exclusion_files_verified': files,
              'additional_service_proof_sha256': sha(additional_path),
              'source_pool_not_opened_or_sampled': True, 'new_independent_sources_selected': False, 'new_GPU_requests': 0}
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('excluded_source_groups', 'original_exclusion_files_verified')}))


if __name__ == '__main__':
    main()
