"""Rebuild in a new directory; compare page text/pixels and Fig.4 bytes."""
from pathlib import Path
import argparse,json,shutil,subprocess,sys
import fitz

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
dest=args.output.resolve();assert not dest.exists() and dest!=root
for item in root.rglob('*'):
    if not item.is_file():continue
    rel=item.relative_to(root)
    if 'v5a_baseline' in rel.parts or '__pycache__' in rel.parts:continue
    if item.suffix in {'.aux','.log','.out','.gz'} or rel.parts[0]=='audit':continue
    target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(item,target)
(dest/'audit').mkdir(exist_ok=True)
for script in ['plot_fig4_v5b.py','build.py','qa_v5b.py']:
    r=subprocess.run([sys.executable,'-B',str(dest/'scripts'/script)],cwd=dest,capture_output=True)
    (dest/'audit'/('reproduce_'+script+'.txt')).write_bytes(r.stdout+r.stderr)
    assert r.returncode==0,(script,(r.stdout+r.stderr).decode(errors='replace')[-4000:])
    print(script+': PASS',flush=True)
records=[]
for stem in ['contractkv_tsc_v5b','contractkv_supplement']:
    a=fitz.open(root/(stem+'.pdf'));b=fitz.open(dest/(stem+'.pdf'));assert len(a)==len(b)
    assert all(x.get_text()==y.get_text() for x,y in zip(a,b))
    assert all(x.get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=False).samples==y.get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=False).samples for x,y in zip(a,b))
    records.append({'file':stem+'.pdf','pages':len(a),'page_text_and_half_scale_pixels_equal':True})
for ext in ['pdf','svg','png']:
    name='figures/fig4_transaction_and_amortization.'+ext
    assert (root/name).read_bytes()==(dest/name).read_bytes(),name
out={'status':'PASS','new_model_requests':0,'fresh_directory_rebuild':True,'manuscripts':records,'regenerated_Fig4_byte_identical':True,'PDF_byte_equality_claimed':False}
(root/'audit/independent_reproduction_v5b.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
