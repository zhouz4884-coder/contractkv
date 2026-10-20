"""Export a clean, checksummed V5b package without baseline/intermediate files."""
from pathlib import Path
import argparse,hashlib,json,zipfile

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
target=a.output.resolve();assert not target.exists(),'Use a new archive path.'
audit_names={'manuscript_QA_v5b.json','independent_reproduction_v5b.json','fig4_contract_v5b.md',
             'original_package_integrity_v1.json','manual_visual_review_v1.json',
             'V5a_to_V5b_source.diff','evidence_locations_v5b.json'}
members=[]
for item in sorted(root.rglob('*')):
    if not item.is_file():continue
    rel=item.relative_to(root)
    if any(x in rel.parts for x in ['__pycache__','v5a_baseline','review']):continue
    if item.suffix in {'.aux','.log','.out','.gz'}:continue
    if rel.parts[0]=='audit' and item.name not in audit_names:continue
    if item.name in {'V5b_package_manifest.json','V5b_release_receipt.json'}:continue
    members.append((item,rel.as_posix()))
manifest={'schema':'contractkv.manuscript-release.v5b','new_model_calls':0,
          'files':[{'path':name,'bytes':item.stat().st_size,'sha256':hashlib.sha256(item.read_bytes()).hexdigest()} for item,name in members]}
manifest_bytes=(json.dumps(manifest,indent=2)+'\n').encode()
(root/'V5b_package_manifest.json').write_bytes(manifest_bytes)
target.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for item,name in members:archive.write(item,'ContractKV_V5b_20261020/'+name)
    archive.writestr('ContractKV_V5b_20261020/V5b_package_manifest.json',manifest_bytes)
with zipfile.ZipFile(target) as archive:
    for row in manifest['files']:
        assert hashlib.sha256(archive.read('ContractKV_V5b_20261020/'+row['path'])).hexdigest()==row['sha256']
receipt={'archive':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
         'verified_members':len(members)+1,'all_manifest_members_verified':True}
(root/'V5b_release_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
