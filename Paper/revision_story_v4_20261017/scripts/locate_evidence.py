"""Index real compiled labels and their source lines; not PDF line numbering."""
from pathlib import Path
import re,csv,json

root=Path(__file__).resolve().parents[1]
def inputs(path,seen=None):
    seen=set() if seen is None else seen
    if path in seen:return []
    seen.add(path);out=[path]
    for name in re.findall(r'\\input\{([^}]+)\}',path.read_text(encoding='utf-8')):
        child=root/(name if name.endswith('.tex') else name+'.tex')
        if child.exists():out+=inputs(child,seen)
    return out
records=[];look={}
def group(text,pos):
    assert text[pos]=='{'
    start=pos+1;depth=1;pos+=1
    while depth:
        if text[pos]=='{':depth+=1
        elif text[pos]=='}':depth-=1
        pos+=1
    return text[start:pos-1],pos
for doc,stem in [('main','contractkv_tsc_story_v4'),('supplement','contractkv_supplement')]:
    labels=[]
    for line in (root/(stem+'.aux')).read_text(encoding='utf-8').splitlines():
        if not line.startswith(r'\newlabel{'):continue
        label,pos=group(line,len(r'\newlabel'));outer,pos=group(line,pos)
        number,pos=group(outer,0);page,pos=group(outer,pos)
        number=re.sub(r'\\mbox\s*\{([^}]+)\}',r'\1',number)
        labels.append((label,number,page))
    files=inputs(root/(stem+'.tex'))
    for label,number,page in labels:
        matches=[]
        for p in files:
            for line,text in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
                if '\\label{'+label+'}' in text:matches.append((p,line))
        assert len(matches)==1,(doc,label,matches)
        p,line=matches[0]
        row={'document':doc,'label':label,'display_number':number,'pdf_page':page,
             'source_file':p.relative_to(root).as_posix(),'tex_source_line':line}
        records.append(row);look[(doc,label)]=row
for label,expected in [('tab:s-raw-orders','S-I'),('tab:s-displacement','S-II'),('tab:s-density','S-III'),('tab:s-mechanisms','S-VI'),('tab:s-native-quality','S-VIII')]:
    assert look[('supplement',label)]['display_number']==expected
with (root/'audit/evidence_locations.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
topics=[('R2.6 input displacement','supplement','tab:s-displacement'),('R3.1 raw order','supplement','tab:s-raw-orders'),
 ('service-template amortization','main','fig:governance'),('four-configuration deployment breadth','main','tab:deployment-width'),
 ('strict full-cost performance','main','fig:performance'),('free-running quality and separate RULER','main','fig:behavior'),
 ('same-engine D0/D1/D2 and rejection','main','sec:ablation'),('10-80 identity scale','supplement','tab:s-density'),
 ('open-arrival SLO and physical KV','main','fig:service'),('frozen benefit gate','main','tab:gate'),
 ('quality baselines','supplement','tab:s-native-quality'),('method responsibilities','supplement','tab:s-mechanisms'),
 ('trust and timing limits','main','sec:trust'),
 ('qualification protocol boundary','main','tab:qualification-protocols'),
 ('independent zero-slack cost supplement','supplement','tab:zeroslack'),
 ('six-source model outcomes','supplement','tab:s-source-results'),
 ('registration trust cases','supplement','tab:s-manifest'),
 ('open-arrival interval','supplement','tab:s-open-ci'),
 ('separate five-family structural controls','supplement','tab:s-five-family-structure'),
 ('same-source structural input comparison','supplement','tab:s-structure-paired'),
 ('original matched-request RPC accounting and missing timers','supplement','tab:s-matched-original-cost'),
 ('actual deployment-client binding boundary','supplement','tab:s-client-binding')]
with (root/'audit/paper_evidence_topics.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['topic']+list(records[0]));w.writeheader()
    for topic,doc,label in topics:w.writerow({'topic':topic,**look[(doc,label)]})
print(json.dumps({'compiled_label_locations':len(records),'topic_entries':len(topics),
                  'line_type':'TeX source lines, not printed PDF line numbers','response_letter_written':False}))
