"""Package only reviewable sources and final assets; retain byte identities."""
from pathlib import Path
import hashlib,json,re,zipfile,sys
import fitz
from PIL import Image,ImageDraw,ImageFont

root=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
qa=json.loads((root/'audit/manuscript_QA.json').read_text())
assert qa['status']=='PASS'
source='\n'.join(p.read_text(encoding='utf-8') for p in sorted((root/'sections').glob('[0-9]*.tex')))
figure_blocks=re.findall(r'\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}',source,re.S)
captions=[re.search(r'\\caption\{(.*?)\}\s*\\label\{fig:([^}]+)\}',block,re.S).groups()
          for block in figure_blocks]
stems=['fig1_architecture','fig2_full_cost_benefits','fig3_coverage_and_fidelity','fig4_transaction_and_amortization','fig5_service_goodput_and_kv_savings','fig6_locality_and_residency']
assert len(captions)==len(stems)==6
review=fitz.open()
for i,(stem,(caption,label)) in enumerate(zip(stems,captions),1):
    page=review.new_page(width=612,height=448)
    page.insert_text((24,26),f'ContractKV | Figure {i}',fontsize=12,color=(.08,.25,.42))
    with fitz.open(root/'figures'/(stem+'.pdf')) as original:page.show_pdf_page(fitz.Rect(24,44,588,320),original,0)
    caption=caption.replace('\\%','%').replace('\\times','x').replace('$','').replace('~',' ').replace('--','-')
    labels=(root/'contractkv_tsc_story_v4.aux').read_text(encoding='utf-8')
    caption=re.sub(r'\\ref\{([^}]+)\}',lambda m:re.search(r'\\newlabel\{'+re.escape(m[1])+r'\}\{\{([^}]+)',labels).group(1),caption)
    assert page.insert_textbox(fitz.Rect(24,330,588,438),caption,fontname='helv',fontsize=8.0,lineheight=1.15)>=0
review.save(root/'figures/Fig1-6_review.pdf',garbage=4,deflate=True)
for stem in ('contractkv_tsc_story_v4','contractkv_supplement'):
    doc=fitz.open(root/(stem+'.pdf'));cards=[]
    for i,page in enumerate(doc,1):
        pix=page.get_pixmap(matrix=fitz.Matrix(.6,.6),alpha=False)
        im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples);im.thumbnail((390,515))
        card=Image.new('RGB',(410,550),'white');card.paste(im,((410-im.width)//2,22));ImageDraw.Draw(card).text((8,4),f'Page {i}',fill='black');cards.append(card)
    sheet=Image.new('RGB',(1640,550*((len(cards)+3)//4)),'#DDE3E8')
    for i,card in enumerate(cards):sheet.paste(card,((i%4)*410,(i//4)*550))
    sheet.save(root/'audit'/(stem+'_layout.png'))

allowed={'.tex','.py','.sh','.md','.json','.jsonl','.csv','.pdf','.svg','.png'}
paths=[p for p in root.rglob('*') if p.is_file() and (p.suffix in allowed or p.name=='requirements.txt')
       and '__pycache__' not in p.parts and p.name!='package_manifest.json']
paths=sorted(paths,key=lambda p:p.relative_to(root).as_posix())
record={'source_root':root.name,'main_pages':qa['manuscripts'][0]['pages'],
        'supplement_pages':qa['manuscripts'][1]['pages'],
        'files':[{'path':p.relative_to(root).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in paths]}
manifest=root/'audit/package_manifest.json'
manifest.write_bytes((json.dumps(record,indent=2)+'\n').encode())
destination=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent.parent/'submission/ContractKV_story_v4_20261017.zip'
destination.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for p in paths+[manifest]:z.write(p,root.name+'/'+p.relative_to(root).as_posix())
with zipfile.ZipFile(destination) as z:
    assert len(z.namelist())==len(paths)+1
    for row in record['files']:
        content=z.read(root.name+'/'+row['path']);assert hashlib.sha256(content).hexdigest()==row['sha256']
print(json.dumps({'zip':str(destination),'members':len(paths)+1,'sha256':sha(destination),'manifest_members_verified':True}))
