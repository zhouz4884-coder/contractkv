"""Graphical ContractKV architecture: dependency, token checks and physical KV."""
from pathlib import Path
import importlib.util,json,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,FancyBboxPatch,FancyArrowPatch,Polygon

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('house',ROOT/'scripts/plot_figures.py')
house=importlib.util.module_from_spec(spec);spec.loader.exec_module(house)
OUT=ROOT/'figures'

def main():
    house.style();fig=plt.figure(figsize=(7.16,3.85));ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,1),ylim=(0,1));ax.set_axis_off()
    blue=house.CKV;teal=house.REUSE;orange=house.COST;gray=house.MUTED;ink=house.INK
    pale='#EDF6FA';green='#C6E5E2';private='#E4E6EA';amber='#FFE2C0';purple='#E8E4F4'
    def text(x,y,s,size=7.1,color=ink,ha='left',weight='normal',va='center'):
        ax.text(x,y,s,fontsize=size,color=color,ha=ha,va=va,weight=weight,linespacing=1.23)
    def box(x,y,w,h,fc='white',ec='#BFCCD6',lw=.7,r=.007):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle=f'round,pad=0.002,rounding_size={r}',fc=fc,ec=ec,lw=lw))
    def arrow(x1,y1,x2,y2,color=gray,style='-'):
        ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',mutation_scale=7.5,color=color,lw=.8,linestyle=style))
    def line(points,color=gray,style='-'):
        ax.plot([p[0] for p in points],[p[1] for p in points],color=color,lw=.75,ls=style)
    def blocks(x,y,w,h,colors,labels=None,edge=teal,fs=6.5):
        step=w/len(colors)
        for i,c in enumerate(colors):
            ax.add_patch(Rectangle((x+i*step,y),step-.0015,h,fc=c,ec=edge,lw=.55))
            if labels:text(x+(i+.5)*step,y+h/2,labels[i],fs,ha='center')
    def stack(x,y,w,h,colors):
        for off in (.012,.006,0):
            blocks(x+off,y+off,w,h,colors,edge='#649B9D')

    text(.020,.965,'Structured requests',8.5,blue,weight='bold')
    text(.260,.965,'ContractKV control plane',8.5,blue,weight='bold')
    text(.830,.965,'Reuse identity',8.5,blue,weight='bold')
    # Request content: the stable document is visibly after a changing field.
    box(.016,.548,.216,.367,fc='#F7FAFC')
    text(.029,.882,'Same template, two requests',7.0,blue,weight='bold')
    for y,label,observation in ((.765,'Request 1','a'),(.630,'Request 2','b')):
        text(.029,y+.071,label,6.9,gray)
        blocks(.029,y,.189,.056,[green,amber,green,purple],['SYS','OBS '+observation,'DOC','Q'],edge='#8BA6B0',fs=6.4)
        ax.plot([.076,.076],[y-.008,y+.067],color=orange,lw=1,ls=(0,(2,2)))
    text(.029,.571,'Native match stops before DOC',6.9,orange)
    arrow(.232,.744,.252,.744,blue)
    # Registered manifest as a document, not a paragraph-only box.
    box(.016,.305,.216,.194,fc='#F7FAFC')
    text(.029,.466,'Registered manifest',7.4,blue,weight='bold')
    ax.add_patch(Polygon([(.031,.337),(.031,.433),(.079,.433),(.092,.418),(.092,.337)],fc='white',ec=blue,lw=.7))
    for yy,c in ((.403,green),(.382,amber),(.361,purple)):ax.add_patch(Rectangle((.041,yy),.038,.009,fc=c,ec='none'))
    text(.108,.416,'Types + dependencies',6.6)
    text(.108,.380,'Authorization',6.6)
    text(.108,.344,'Template version',6.6)
    line([(.232,.400),(.242,.400),(.242,.575),(.261,.575)],blue,style='--')
    # CALC: a dependency DAG beside a visually selected layout ladder.
    box(.255,.548,.263,.367,fc='#EEF4FB',ec=blue)
    text(.268,.882,'(1) CALC layout compiler',7.9,blue,weight='bold')
    text(.270,.825,'Dependencies',6.8,gray)
    nodes={'SYS':(.306,.757),'DOC':(.275,.658),'OBS':(.350,.658),'Q':(.350,.577)}
    for one,two in (('SYS','DOC'),('SYS','OBS'),('DOC','Q'),('OBS','Q')):
        xx,yy=nodes[one];xx2,yy2=nodes[two]
        arrow(xx+.027,yy-.005,xx2+.027,yy2+.047,blue)
    for name,(xx,yy) in nodes.items():
        box(xx,yy,.055,.047,fc=green if name in ('SYS','DOC') else (amber if name=='OBS' else purple),ec=blue,r=.003)
        text(xx+.0275,yy+.0235,name,6.5,ha='center')
    text(.424,.825,'Layouts',6.8,gray)
    layouts=[[green,amber,green,green,purple],[green,green,green,amber,purple],[green,green,amber,green,purple]]
    for i,colors in enumerate(layouts):
        yy=.751-i*.075
        if i==1:box(.418,yy-.009,.086,.055,fc='white',ec=blue,lw=1.1,r=.003)
        blocks(.423,yy,.076,.037,colors,edge='#7F98AC')
    arrow(.411,.696,.419,.696,blue)
    arrow(.519,.744,.538,.744,blue)
    # Certification: alternate witness sources and explicit paired token rows.
    box(.542,.548,.263,.367,fc='#FFF7EE',ec=orange)
    text(.555,.882,'(2) Scoped certification',7.9,blue,weight='bold')
    text(.555,.826,'Witness source (one protocol)',6.9,gray)
    box(.556,.747,.107,.052,fc='white',ec=blue,r=.004)
    box(.687,.747,.104,.052,fc='white',ec=blue,r=.004)
    text(.609,.773,'Qualified route',6.4,ha='center')
    text(.739,.773,'First raw reply',6.4,ha='center')
    text(.675,.773,'or',6.5,gray,ha='center')
    text(.555,.706,'ref.',6.5,gray)
    text(.555,.644,'cand.',6.5,gray)
    for yy in (.683,.621):blocks(.607,yy,.178,.044,[green]*4+[amber],['y1','y2','…','yL','EOS'],edge='#83AAA8',fs=6.4)
    for xx in (.623,.659,.694,.730):arrow(xx,.679,xx,.669,teal)
    text(.555,.577,'Token margins + natural-stop check',6.7,orange)
    arrow(.674,.546,.674,.505,orange)
    # Template-scoped registration with several query decisions referring to one prefix.
    box(.826,.548,.158,.367,fc='#EEF4FB',ec=blue)
    text(.838,.876,'(4) Template certificate',7.0,blue,weight='bold')
    text(.840,.818,'scope',6.3,gray);text(.893,.818,'layout',6.3,gray);text(.944,.818,'prefix',6.3,gray)
    for yy,q in ((.758,'q1'),(.700,'q2')):
        line([(.839,yy-.022),(.972,yy-.022)],'#CBD5DE')
        text(.846,yy,q,7.1);text(.908,yy,'L*',7.1,ha='center');text(.960,yy,'Hs',7.1,teal,ha='center')
    text(.840,.632,'Identity + authorization',6.3)
    text(.840,.583,'Version + epoch',6.6)
    # A real engine boundary and physical candidate/shared block structures.
    box(.255,.137,.729,.364,fc='#F6F8FA',ec='#AEBFCB')
    text(.268,.474,'Serving engine: verifier executor + native KV manager (vLLM V1)',7.7,blue,weight='bold')
    text(.268,.427,'(3) PSTP: atomic promotion',7.5,teal,weight='bold')
    stack(.278,.321,.102,.052,[green]*4+[amber,purple])
    text(.333,.278,'Private candidate',6.7,gray,ha='center')
    line([(.278,.310),(.345,.310)],teal)
    text(.309,.243,'stable only',6.5,teal,ha='center')
    arrow(.393,.347,.417,.347,teal)
    ax.add_patch(Polygon([(.455,.403),(.491,.347),(.455,.291),(.419,.347)],fc='white',ec=teal,lw=.9))
    text(.455,.347,'PASS +\nbinding',6.5,ha='center')
    arrow(.492,.347,.558,.347,teal)
    text(.524,.381,'commit',6.5,teal,ha='center')
    arrow(.455,.290,.455,.268,house.REJECT)
    text(.455,.245,'Abort: no promotion',6.5,house.REJECT,ha='center')
    text(.644,.427,'Shared prefix index',7.1,blue,ha='center',weight='bold')
    box(.565,.310,.159,.066,fc='white',ec=teal,r=.004)
    text(.645,.344,'Hs → [b0, b1, …]',6.6,teal,ha='center')
    arrow(.644,.309,.644,.254,teal)
    for j in range(2):
        blocks(.576,.222-j*.036,.137,.027,[green,green,private,green,private,private],edge='#A0B1BD')
    text(.644,.158,'Native GPU block pool',6.4,gray,ha='center')
    # The physical prefix is shared only by requests of the same authorized template.
    text(.851,.427,'Authorized reuse',7.1,blue,ha='center',weight='bold')
    for yy,name in ((.321,'Tenant A'),(.215,'Tenant B')):
        text(.770,yy+.070,name,6.6,gray)
        blocks(.770,yy,.192,.048,[green]*4+[purple,purple],edge='#7DABA9')
    line([(.725,.344),(.747,.344),(.747,.239)],teal)
    arrow(.747,.344,.769,.344,teal);arrow(.747,.239,.769,.239,teal)
    line([(.902,.548),(.902,.513),(.749,.513),(.749,.393)],blue,style='--')
    text(.856,.157,'same prefix + private suffix',6.2,gray,ha='center')
    # Business path is separate from candidate promotion, avoiding a second model check.
    box(.016,.137,.216,.116,fc='#F7FAFC')
    text(.029,.221,'Business request',7.1,blue,weight='bold')
    text(.029,.176,'Scope lookup → qualified / raw',6.6)
    arrow(.233,.195,.267,.185,blue)
    box(.269,.153,.128,.064,fc='white',ec=blue,r=.004)
    text(.333,.185,'Prefill / decode',6.6,blue,ha='center')
    arrow(.333,.151,.333,.132,blue)
    blocks(.283,.103,.10,.023,['#C9DDEE']*5,edge='#7896AF')
    text(.399,.114,'Output tokens',6.3,gray)
    text(.5,.067,'Solid: execution / KV state     Dashed: identity / policy binding',6.7,gray,ha='center')
    text(.5,.025,'Qualified state may outlive native block residency; a miss recomputes the prefix.',6.7,gray,ha='center')
    house.save(fig,OUT,'fig1_architecture')
    record={'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'figure':house.QA[-1],
      'design':'dependency graph + layout candidates + token-path checks + scope registry + atomic cache publication',
      'two_witness_protocols_evaluated_separately':True,'second_model_verification_at_commit':False,
      'invented_offloading_or_scheduler':False,'illustrative_numeric_certificate_fields':False,'new_measurements':0}
    (OUT/'architecture_QA_v9.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    print(json.dumps({'outside':record['figure']['text_outside_canvas'],'collisions':record['figure']['text_bbox_collisions']}))
if __name__=='__main__':main()
