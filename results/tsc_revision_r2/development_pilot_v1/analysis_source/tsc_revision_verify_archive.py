"""Verify byte transport and every immutable R1 raw archive member."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import tarfile


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    parts=json.loads((a.root/'raw_evidence_parts_manifest_v1.json').read_text()); full=hashlib.sha256()
    declared=json.loads((a.root/'raw_evidence_archive_manifest_v1.json').read_text())
    if (parts['archive'],parts['archive_sha256'])!=(declared['archive'],declared['archive_sha256']):
        raise ValueError('Archive manifests disagree')
    part_names=[item['file'] for item in parts['parts']]
    if not part_names or len(part_names)!=len(set(part_names)): raise ValueError('Missing or duplicate archive parts')
    total_bytes=0
    for item in parts['parts']:
        data=(a.root/item['file']).read_bytes()
        if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']: raise ValueError('Part mismatch')
        full.update(data); total_bytes+=len(data)
    if total_bytes!=declared['archive_bytes']: raise ValueError('Archive byte count mismatch')
    if full.hexdigest()!=parts['archive_sha256']: raise ValueError('Reassembled hash mismatch')
    if hashlib.sha256(a.archive.read_bytes()).hexdigest()!=full.hexdigest(): raise ValueError('Archive mismatch')
    with (a.root/'raw_evidence_inventory_v1.csv').open(encoding='utf-8',newline='') as stream:
        inventory_rows=list(csv.DictReader(stream))
    inventory={r['path']:r for r in inventory_rows}
    if len(inventory)!=len(inventory_rows) or len(inventory)!=declared['member_files']:
        raise ValueError('Inventory member count or duplicate paths')
    with tarfile.open(a.archive,'r:gz') as archive:
        members=archive.getmembers()
        if len(members)!=len(inventory): raise ValueError('Archive membership count')
        names=[member.name for member in members]
        if len(names)!=len(set(names)) or set(names)!=set(inventory): raise ValueError('Archive member set mismatch')
        for member in members:
            if not member.isfile() or member.name not in inventory: raise ValueError('Unexpected member')
            row=inventory[member.name]; data=archive.extractfile(member).read()
            if len(data)!=int(row['bytes']) or hashlib.sha256(data).hexdigest()!=row['sha256']: raise ValueError('Member hash mismatch')
    result={'schema_version':'tsc-revision-local-archive-verification.v1','parts':len(parts['parts']),
            'archive_sha256':full.hexdigest(),'members_verified':len(inventory),'all_hashes_match':True,
            'does_not_imply_scientific_success':True}
    a.output.write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))


if __name__=='__main__': main()
