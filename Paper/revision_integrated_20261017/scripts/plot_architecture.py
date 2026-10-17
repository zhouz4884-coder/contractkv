"""Evidence-aligned vector architecture: prefix gap, qualification, publication."""
from pathlib import Path
import importlib.util,json,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,Rectangle,FancyArrowPatch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('house',ROOT/'scripts/plot_figures.py')
house=importlib.util.module_from_spec(spec);spec.loader.exec_module(house)
OUT=ROOT/'figures'

def main():
    house.style();fig=plt.figure(figsize=(7.16,3.35));ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,1),ylim=(0,1));ax.set_axis_off()
    blue=house.CKV;teal=house.REUSE;orange=house.COST;gray=house.MUTED;ink=house.INK
    def box(x,y,w,h,fc='white',ec='#CBD6DF',lw=.65):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.004,rounding_size=0.008',fc=fc,ec=ec,lw=lw))
    def text(x,y,s,size=7.4,color=ink,ha='left',weight='normal',va='center'):
        ax.text(x,y,s,fontsize=size,color=color,ha=ha,va=va,weight=weight,linespacing=1.35)
    def arrow(x1,y1,x2,y2,color=gray,style='-'):
        ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',mutation_scale=8,color=color,lw=.8,linestyle=style))
    def strip(x,y,width,labels,types,h=.064,obs=None):
        sizes={'SYS':.16,'OBS':.20,'DOC':.43,'Q':.17,'PRIVATE':.30,'PREFIX':.64}
        total=sum(sizes[z] for z in labels);pos=x
        for label,kind in zip(labels,types):
            ww=width*sizes[label]/total
            fc={'s':'#C8E7E5','m':'#FFE4C7','q':'#E5E4F3'}[kind]
            edge=teal if kind=='s' else (orange if kind=='m' else '#8D8AA8')
            ax.add_patch(Rectangle((pos,y),ww-.002,h,fc=fc,ec=edge,lw=.6))
            text(pos+ww/2,y+h/2,label+' '+obs if label=='OBS' and obs else label,size=6.6,ha='center')
            pos+=ww
    for x,w in ((.012,.268),(.296,.390),(.702,.286)):box(x,.12,w,.84,fc='#FAFCFD')
    text(.026,.918,'(a) A structural prefix gap',8.6,blue,weight='bold')
    text(.310,.918,'(b) Compile and qualify',8.6,blue,weight='bold')
    text(.716,.918,'(c) Publish and reuse',8.6,blue,weight='bold')
    text(.026,.842,'One template; changing metadata',7.2)
    text(.026,.771,'Request 1',7.1,gray);strip(.026,.665,.238,['SYS','OBS','DOC','Q'],['s','m','s','q'],obs='a')
    text(.026,.594,'Request 2',7.1,gray);strip(.026,.488,.238,['SYS','OBS','DOC','Q'],['s','m','s','q'],obs='b')
    for low,high in ((.650,.744),(.473,.567)):
        ax.plot([.066,.066],[low,high],color=orange,lw=.9,ls=(0,(2,2)))
    text(.026,.391,'Native match ends at the change.',7.2,orange)
    text(.026,.302,'Stable documents repeat\nafter that boundary.',7.4)
    text(.026,.190,'Repeated text ≠ reusable prefix',7.2,blue,weight='bold')
    arrow(.275,.69,.312,.69,blue)
    box(.316,.595,.348,.255,fc='#EFF5FB',ec=blue)
    text(.331,.812,'CALC',8.3,blue,weight='bold')
    text(.331,.752,'Dependency-valid layout; exact token identity',7.2)
    strip(.331,.641,.317,['SYS','DOC','OBS','Q'],['s','s','m','q'])
    arrow(.490,.590,.490,.553,blue)
    box(.316,.319,.348,.224,fc='#FFF7EF',ec=orange)
    text(.331,.505,'Scoped behavioral certification',8.0,blue,weight='bold')
    text(.331,.444,'Witness protocol (evaluated separately)',7.0,gray)
    text(.331,.393,'Deployment: qualified route  |  Query: first raw reply',6.7)
    text(.331,.344,'Teacher-forced token-path + EOS checks',7.2,orange)
    arrow(.490,.315,.490,.276,teal)
    box(.316,.157,.348,.111,fc='#EDF7F5',ec=teal)
    text(.331,.231,'Evidence bound to layout, scope and execution',7.1)
    text(.331,.184,'Failed / ineligible → raw route',7.2,gray)
    box(.720,.673,.250,.178,fc='#EFF5FB',ec=blue)
    text(.732,.818,'Service-Template Certificate',7.7,blue,weight='bold')
    text(.732,.758,'Identity · scope · authorization\nStable-prefix hash · lifecycle epoch',7.0)
    ax.plot([.664,.694,.694],[.21,.21,.546],color=teal,lw=.8)
    arrow(.694,.546,.720,.546,teal)
    box(.720,.459,.250,.175,fc='#EDF7F5',ec=teal)
    text(.732,.600,'PSTP: atomic publication',7.7,teal,weight='bold')
    text(.732,.542,'PASS + valid binding → commit\nFAIL → no candidate promotion',7.0)
    arrow(.845,.671,.845,.639,blue,style='--')
    arrow(.845,.456,.845,.416,teal)
    text(.732,.390,'Same template, authorized tenants',7.2,blue,weight='bold')
    strip(.732,.300,.223,['PREFIX','PRIVATE'],['s','q'],h=.055)
    strip(.732,.210,.223,['PREFIX','PRIVATE'],['s','q'],h=.055)
    text(.732,.286,'Tenant A',6.5,gray,va='top');text(.732,.196,'Tenant B',6.5,gray,va='top')
    text(.5,.070,'Qualification permits reuse; native cache residency determines the realized hit.',7.1,gray,ha='center')
    house.save(fig,OUT,'fig1_architecture')
    record={'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'figure':house.QA[-1],'design':'prefix gap -> scoped qualification -> authorized transactional reuse',
            'two_witness_protocols_evaluated_separately':True,'second_model_verification_at_commit':False,
            'illustrative_numeric_certificate_fields':False,'new_performance_measurements':0}
    (OUT/'architecture_QA_v8.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    print(json.dumps({'outside':record['figure']['text_outside_canvas'],'collisions':record['figure']['text_bbox_collisions']}))
if __name__=='__main__':main()
