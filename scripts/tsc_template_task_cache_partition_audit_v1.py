"""CPU audit of actual sharing partitions, distinct from salt-byte equality."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

STUDY = Path('results/tsc_template_task_serving_20261019')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def lines(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def main(workspace, evidence, output):
    proof = read(workspace / STUDY / 'formal_local_independent_recompute_v1.json')
    restore = read(workspace / STUDY / 'formal_local_archive_verification_v1.json')
    assert proof['status'] == restore['status'] == 'PASS'
    assert evidence == Path(restore['restore_root']).resolve() and not output.exists()
    study = evidence / STUDY
    cells = []
    global_salts = defaultdict(set)
    for job in read(study / 'formal_protocol_v1.json')['jobs']:
        groups, tenants, counts, reference_groups = defaultdict(set), defaultdict(set), defaultdict(int), defaultdict(set)
        for row in lines(study / 'runs' / job['id'] / 'attempt1/responses.jsonl'):
            if row['row_type'] == 'business':
                source = row['source_group']
                groups[source].add(row['result']['actual_wire_cache_salt'])
                tenants[source].add(row['tenant'])
                counts[source] += 1
                global_salts[job['model'], source].add(row['result']['actual_wire_cache_salt'])
            elif row['row_type'] == 'reference_generation':
                reference_groups[row['source_group']].add(row['result']['actual_wire_cache_salt'])
        assert len(groups) == 6 and sum(counts.values()) == 384
        assert all(len(salts) == 1 and len(tenants[source]) == 8 and counts[source] == 64 for source, salts in groups.items())
        all_business = set().union(*groups.values())
        assert len(all_business) == 6
        all_reference = set().union(*reference_groups.values()) if reference_groups else set()
        assert all_business.isdisjoint(all_reference)
        assert all(len(salts) == 1 for salts in reference_groups.values())
        assert len(reference_groups) == (0 if job['policy'] == 'Raw-authorized' else 3)
        cells.append(dict(cell=job['id'], model=job['model'], load=job['load'], repeat=job['repeat'], policy=job['policy'],
            business_groups=6, requests_per_group=64, tenants_per_group=8,
            reference_groups=len(reference_groups), canary_groups_disjoint_from_business=True,
            same_source_iff_same_wire_salt=True,
            partition_signature=sorted((source, counts[source], sorted(tenants[source])) for source in groups)))
    for model, load, repeat in {(r['model'], r['load'], r['repeat']) for r in cells}:
        matches=[r for r in cells if (r['model'],r['load'],r['repeat'])==(model,load,repeat)]
        assert len(matches)==3 and matches[0]['partition_signature']==matches[1]['partition_signature']==matches[2]['partition_signature']
    result=dict(status='PASS_ACTUAL_SHARING_PARTITIONS_EQUAL_OPAQUE_SALT_BYTES_ROTATE', new_GPU_requests=0,
        changes_to_measurements_or_policy=False, archive_sha256=proof['archive_sha256'], cells=cells,
        actual_cells=len(cells), actual_business=10368, all_policy_triplets_have_identical_sharing_relation=True,
        all_reference_canaries_use_separate_groups=True,
        literal_salt_bytes_identical_across_fresh_servers=all(len(x)==1 for x in global_salts.values()),
        code_cause='Frozen ServingAuthority creates CacheAuthority(secrets.token_bytes(32), ...); CacheAuthority._salt uses this key in HMAC. Each fresh cell has a fresh engine and authority.',
        boundary='Opaque salt strings differ across fresh engines. Equivalence here concerns the measured six source groups, 64 business calls and eight authorized tenants per group, not cross-engine reuse or a persistent common secret.',
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:result[k] for k in ['status','actual_cells','actual_business','literal_salt_bytes_identical_across_fresh_servers','new_GPU_requests']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['workspace','evidence-root','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();main(args.workspace.resolve(),args.evidence_root.resolve(),args.output.resolve())
