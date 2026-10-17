"""Compact, information-focused revision figures with explicit metric roles."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.font_manager import findfont
from matplotlib.patches import Patch,Rectangle
from matplotlib.text import Text
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('old_style',ROOT/'scripts/style_base.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
CKV=old.CKV;REUSE=old.SAFE;COST=old.RISK;REJECT=old.UNSAFE
RAW=old.NATIVE;LIGHT=old.NATIVE_LIGHT;INK=old.INK;MUTED=old.MUTED;GRID=old.GRID
D1='#8FA3B8';PALE=old.PALE_TEAL
QA=[]


def style():
    old.set_style(8)
    plt.rcParams.update({'axes.titlesize':8.4,'axes.labelsize':7.5,'xtick.labelsize':7.1,
        'ytick.labelsize':7.1,'legend.fontsize':7.0,'savefig.bbox':None,'axes.linewidth':.7,
        'svg.hashsalt':'contractkv-v10-20261017','figure.facecolor':'white','axes.facecolor':'white'})


def title(ax,letter,text,pad=8):ax.set_title(f'({letter}) {text}',loc='left',pad=pad,fontweight='bold')
def gy(ax):ax.set_axisbelow(True);ax.grid(axis='y',color=GRID,lw=.55)
def gx(ax):ax.set_axisbelow(True);ax.grid(axis='x',color=GRID,lw=.55)
def tag(fig,text):fig.text(.5,.965,text,ha='center',va='top',fontsize=7.0,color=MUTED)


def save(fig,out,stem):
    fig.canvas.draw();renderer=fig.canvas.get_renderer();canvas=fig.bbox
    outside=[];text_boxes=[]
    for t in fig.findobj(Text):
        if not t.get_visible() or not t.get_text().strip():continue
        b=t.get_window_extent(renderer)
        text_boxes.append((t.get_text(),b))
        if b.x0 < -1 or b.y0 < -1 or b.x1 > canvas.width+1 or b.y1 > canvas.height+1:
            outside.append({'text':t.get_text(),'bbox':[b.x0,b.y0,b.x1,b.y1]})
    collisions=[]
    for i,(one,a) in enumerate(text_boxes):
        for two,b in text_boxes[i+1:]:
            width=min(a.x1,b.x1)-max(a.x0,b.x0);height=min(a.y1,b.y1)-max(a.y0,b.y0)
            if width>1.0 and height>1.0:
                collisions.append({'one':one,'two':two,'overlap_pixels':[width,height]})
    files={}
    for ext in ('pdf','svg','png'):
        p=out/(stem+'.'+ext);kw={}
        if ext=='pdf':kw['metadata']={'Creator':'ContractKV measured-data figures v10','CreationDate':None,'ModDate':None}
        if ext=='svg':kw['metadata']={'Date':None}
        if ext=='png':kw['dpi']=600
        fig.savefig(p,**kw)
        if ext=='svg':p.write_bytes(('\n'.join(x.rstrip() for x in p.read_text(encoding='utf-8').splitlines())+'\n').encode())
        files[ext]={'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    QA.append({'figure':stem,'width_in':fig.get_figwidth(),'height_in':fig.get_figheight(),
               'text_outside_canvas':outside,'text_bbox_collisions':collisions,'exports':files})
    plt.close(fig)


def figure2(d,out):
    style();fig=plt.figure(figsize=(7.16,2.80))
    gs=fig.add_gridspec(1,3,width_ratios=[.93,1.13,1.04],left=.075,right=.982,
                       bottom=.28,top=.79,wspace=.46)
    a,b,c=[fig.add_subplot(gs[0,i]) for i in range(3)]
    tag(fig,'Strict query-scoped protocol · faithful 16K inputs · zero tool slack')
    x=np.arange(3);labels=['Qwen3\n8B','Mistral\n7B','Llama3.1\n8B'];r=d['strict']
    values=[z['wall_multiplier'] for z in r]
    a.bar(x,values,.58,color=CKV,edgecolor=INK,lw=.5)
    for i,z in enumerate(r):
        a.text(i,z['wall_multiplier']+.10,f"{z['wall_multiplier']:.3f}×",ha='center',color=CKV,
               weight='bold',fontsize=9.2 if i==0 else 8.0)
    a.axhline(1,color=RAW,ls=(0,(3,2)),lw=.8)
    a.text(.98,.92,'Raw = 1×',transform=a.transAxes,ha='right',color=MUTED,fontsize=6.8)
    a.set(xticks=x,xticklabels=labels,ylim=(0,2),yticks=[0,.5,1,1.5,2],ylabel='Full wall throughput / Raw')
    title(a,'a','Full-cost throughput');gy(a)
    raw=np.array([z['raw_business_prefill_per_repeat']/1e6 for z in r])
    business=np.array([z['CKV_business_prefill_per_repeat']/1e6 for z in r])
    verify=np.array([z['qualification_prefill_per_repeat']/1e6 for z in r]);w=.32
    b.bar(x-w/2,raw,w,color=LIGHT,ec=RAW,lw=.55)
    b.bar(x+w/2,business,w,color=CKV,ec=INK,lw=.45)
    b.bar(x+w/2,verify,w,bottom=business,color=COST,ec=COST,lw=.5)
    for i,z in enumerate(r):
        b.text(i-w/2,raw[i]+.15,f'{raw[i]:.2f}',ha='center',fontsize=6.8,color=MUTED)
        b.text(i+w/2,business[i]+verify[i]+.15,f'{business[i]+verify[i]:.2f}',ha='center',fontsize=6.8,color=CKV,weight='bold')
        b.text(i,max(raw[i],business[i]+verify[i])+.75,f"−{z['net_prefill_reduction_pct']:.1f}%",ha='center',color=CKV,fontsize=8.5 if i==0 else 7.4,weight='bold')
        b.text(i,-.33,f'cert. +{verify[i]:.3f}M',transform=b.get_xaxis_transform(),ha='center',fontsize=6.5,color=COST)
        b.plot([i,i+w],[business[i]+verify[i]]*2,color=COST,lw=2.0,solid_capstyle='butt')
    b.set(xticks=x,xticklabels=labels,ylim=(0,9),yticks=[0,3,6,9],ylabel='New prefill (million tokens / run)')
    title(b,'b','Business + certification');gy(b)
    raw_mean=np.array([z['raw_ready_mean_ms']/1000 for z in r]);ckv_mean=np.array([z['CKV_ready_mean_ms']/1000 for z in r])
    c.bar(x-w/2,raw_mean,w,color=LIGHT,ec=RAW,lw=.55)
    c.bar(x+w/2,ckv_mean,w,color=CKV,ec=INK,lw=.45)
    for i,z in enumerate(r):
        c.text(i-w/2,raw_mean[i]+.13,f'{raw_mean[i]:.2f}',ha='center',color=MUTED,fontsize=6.8)
        c.text(i+w/2,ckv_mean[i]-.13,f'{ckv_mean[i]:.2f}',ha='center',va='top',color='white',fontsize=6.8,weight='bold')
        c.text(i,max(raw_mean[i],ckv_mean[i])+.67,f"−{z['ready_mean_reduction_pct']:.1f}%",ha='center',color=CKV,fontsize=8.5 if i==0 else 7.4,weight='bold')
    c.set(xticks=x,xticklabels=labels,ylim=(0,6.5),yticks=[0,2,4,6],ylabel='Mean readiness TTFT (s)')
    title(c,'c','Mean readiness TTFT');gy(c)
    c.text(.5,-.33,'Future requests · frozen wave clock',transform=c.transAxes,ha='center',fontsize=6.3,color=MUTED)
    fig.legend(handles=[Patch(fc=LIGHT,ec=RAW,label='Raw'),Patch(fc=CKV,ec=INK,label='ContractKV'),
                        Patch(fc=COST,ec=COST,label='Certification work in (b)')],
               loc='lower center',bbox_to_anchor=(.5,.005),ncol=3,fontsize=7,columnspacing=2)
    save(fig,out,'fig2_full_cost_benefits')



def figure3(d,out):
    style();fig=plt.figure(figsize=(3.45,4.65))
    fig.text(.5,.975,'Faithful held-out · query-scoped protocol',ha='center',va='top',fontsize=6.6,color=MUTED)
    a=fig.add_axes([.255,.685,.71,.20]);values=np.array([[r['coverage_pct'] for r in z['family_coverage']] for z in d['strict']])
    cmap=LinearSegmentedColormap.from_list('coverage',['#EFF8F5','#087C70'])
    for i,z in enumerate(d['strict']):
        for j,r in enumerate(z['family_coverage']):
            inherited=r['inherited_L0'];color='#EDF0F2' if inherited else cmap(values[i,j]/70)
            a.add_patch(Rectangle((j-.5,i-.5),1,1,fc=color,ec='white',lw=1.5))
            if inherited:a.add_patch(Rectangle((j-.5,i-.5),1,1,fc='none',ec='#B6BEC5',lw=.4,hatch='///'))
            label='Inherited L0\n0 / 810' if inherited else f"{r['coverage_pct']:.1f}%\n{r['compiled_pairs']} / 810"
            a.text(j,i,label,ha='center',va='center',fontsize=7.1,color=MUTED if inherited else ('white' if values[i,j]>50 else INK),weight='normal' if inherited else 'bold',bbox=dict(fc=color,ec='none',pad=.2))
    a.set(xlim=(-.5,1.5),ylim=(2.5,-.5),xticks=[0,1],xticklabels=['HotpotQA','RepoBench'],yticks=[0,1,2],yticklabels=['Qwen3-8B','Mistral-7B','Llama3.1-8B'])
    a.tick_params(length=0,labelsize=6.8)
    for spine in a.spines.values():spine.set_visible(False)
    title(a,'a','Compiled coverage',pad=7)
    a.text(.5,-.24,'810 future pairs / model / task family',transform=a.transAxes,ha='center',fontsize=6.3,color=MUTED)

    fig.text(.09,.614,'Separate RULER audit · bounded inputs · cold + fan-out',fontsize=6.1,color=MUTED)
    fig.lines.append(plt.Line2D([.09,.95],[.632,.632],transform=fig.transFigure,color=GRID,lw=.6))
    for xx,r in zip((.23,.52,.81),d['restored']['ruler_audit']):
        fig.text(xx,.586,r['model'],ha='center',fontsize=6.5,color=MUTED)
        fig.patches.append(Rectangle((xx-.11,.558),.22,.011,transform=fig.transFigure,fc=LIGHT,ec='none'))
        fig.patches.append(Rectangle((xx-.11,.558),.22*r['coverage_pct']/100,.011,transform=fig.transFigure,fc=D1,ec='none'))
        fig.text(xx,.534,f"{r['compiled']} / {r['pairs']}",ha='center',fontsize=6.6,color=MUTED)
    b=fig.add_axes([.09,.255,.86,.22]);b.set_axis_off();title(b,'b','Observed output-ID differences',pad=7)
    for yy,r,label in zip((.90,.71),d['behavior_audits'],('Bounded-input (50 sources)','Faithful held-out (6 sources)')):
        b.text(0,yy,label,fontsize=6.9,va='center');b.text(1,yy,f"0 / {r['compiled_future_pairs']:,}",ha='right',va='center',fontsize=8.1,color=CKV,weight='bold')
    b.axhline(.58,color=GRID,lw=.6);b.text(0,.48,'Compiled subset: raw-reference score > 0',fontsize=6.6,color=MUTED)
    for yy,name,r in zip((.34,.18,.02),('Qwen','Mistral','Llama'),d['strict']):
        ratio=r['raw_positive_compiled_future_pairs']/r['compiled_future_pairs'];b.text(0,yy,name,fontsize=6.8,va='center')
        b.add_patch(Rectangle((.27,yy-.026),.40,.052,fc='#E2E8EB',ec='none'));b.add_patch(Rectangle((.27,yy-.026),.40*ratio,.052,fc=REUSE,ec='none'))
        b.text(1,yy,f"{r['raw_positive_compiled_future_pairs']} / {r['compiled_future_pairs']}",ha='right',va='center',fontsize=7,color=REUSE,weight='bold')
    b.set(xlim=(0,1),ylim=(-.035,1),xticks=[],yticks=[])
    c=fig.add_axes([.07,.025,.89,.16]);c.set_axis_off();title(c,'c','Logged Qwen / HotpotQA sequence',pad=6)
    labels=[('Raw t0','7 IDs',RAW),('PASS','same scope',REUSE),('COMMITTED','888 blocks',CKV),('Later t3','same 7 IDs',REUSE)]
    for i,(first,second,color) in enumerate(labels):
        xx=i*.255;c.add_patch(Rectangle((xx,.36),.225,.42,fc='white',ec=color,lw=.65));c.text(xx+.1125,.57,first+'\n'+second,ha='center',va='center',fontsize=6.2,linespacing=1.4)
        if i<3:c.annotate('',xy=(xx+.255,.57),xytext=(xx+.229,.57),arrowprops=dict(arrowstyle='->',lw=.7,color=MUTED))
    c.text(.5,.10,'Later native hit: 14,240 tokens · records in artifact',ha='center',fontsize=6.2,color=MUTED)
    c.set(xlim=(-.01,1),ylim=(0,1),xticks=[],yticks=[]);save(fig,out,'fig3_coverage_and_fidelity')


def figure4(d,out):
    style();fig=plt.figure(figsize=(3.45,4.55))
    fig.text(.08,.963,'(a) Certificate amortization',fontsize=8.2,weight='bold')
    a1=fig.add_axes([.27,.772,.66,.092]);a2=fig.add_axes([.27,.542,.66,.092])
    for ax,field,lim,label,fmt,headline,y in [(a1,'calls_per_trace',150,'Verifier calls / trace','{:.0f}','25× fewer calls',.902),(a2,'unhidden_ms_per_future_request',31,'Unhidden ms / future request','{:.2f}','7.7× lower cost',.672)]:
        values=[r[field] for r in d['granularity']];ax.barh([1,0],values,.51,color=[LIGHT,CKV],ec=[RAW,INK],lw=.45)
        for yy,v in zip([1,0],values):ax.text(v+lim*.035,yy,fmt.format(v),va='center',fontsize=7.1,color=MUTED if yy else CKV,weight='bold')
        ax.set(yticks=[1,0],yticklabels=['Session','Template'],xlim=(0,lim),xlabel=label,xticks=[0,50,100,150] if ax is a1 else [0,10,20,30]);ax.tick_params(labelsize=6.8);ax.xaxis.label.set_fontsize(6.8);gx(ax)
        fig.text(.27,y,headline,fontsize=11,color=CKV,weight='bold')
    fig.text(.08,.451,'(b) Fail-closed promotion',fontsize=8.2,weight='bold')
    b=fig.add_axes([.08,.327,.86,.087]);b.set_axis_off()
    for i,(label,col) in enumerate([('Harmful\ncandidate',RAW),('Certification\nFAIL',REJECT),('0 candidate blocks\npromoted',CKV)]):
        xx=i*.35;b.add_patch(Rectangle((xx,.12),.30,.78,fc='white',ec=col,lw=.75));b.text(xx+.15,.51,label,ha='center',va='center',fontsize=6.6,color=col)
        if i<2:b.annotate('',xy=(xx+.35,.51),xytext=(xx+.305,.51),arrowprops=dict(arrowstyle='->',color=MUTED,lw=.7))
    b.set(xlim=(-.01,1.01),ylim=(0,1));fig.text(.5,.303,'8B and 14B TP2: each 10/10 harmful candidates rejected',ha='center',fontsize=6.1,color=MUTED)
    fig.text(.08,.247,'(c) Goodput under governance',fontsize=8.2,weight='bold')
    c=fig.add_axes([.24,.096,.53,.14]);comparison=[d['restored']['native_d0']]+d['d1_d2'];c.barh([2,1,0],[r['goodput'] for r in comparison],.46,color=[RAW,D1,CKV],ec=INK,lw=.45)
    for yy,r in zip([2,1,0],comparison):
        c.errorbar(r['goodput'],yy,xerr=[[r['goodput']-r['min']],[r['max']-r['goodput']]],fmt='none',ecolor=INK,lw=.7,capsize=2)
        c.text(.65 if yy<2 else .19,yy,f"{r['goodput']:.3f}",ha='center' if yy<2 else 'left',va='center',fontsize=7,color='white' if yy==0 else INK,weight='bold')
    c.set(yticks=[2,1,0],yticklabels=['D0','D1','D2'],xlim=(0,1.85),xticks=[0,.8,1.6]);c.tick_params(labelsize=6.8);gx(c)
    fig.text(.87,.158,'97.0%\nof D1',ha='center',va='center',fontsize=9.0,color=CKV,weight='bold',linespacing=1.5)
    fig.text(.50,.031,'500-ms SLO req/s · whiskers: 5-repeat min–max',ha='center',fontsize=6.2,color=MUTED)
    fig.text(.50,.010,'Verifier calls / trace: D0 = 0, D1 = 0, D2 = 4',ha='center',fontsize=6.2,color=COST)
    save(fig,out,'fig4_transaction_and_amortization')


def figure5(d,out):
    style();fig=plt.figure(figsize=(3.45,4.7));fig.text(.5,.979,'Deployment-template studies · separate protocols',ha='center',va='top',fontsize=6.4,color=MUTED)
    a=fig.add_axes([.16,.585,.79,.315]);title(a,'a','Open arrival: 500-ms SLO',pad=7)
    rows=d['open_arrival_load'];x=[r['load_pct'] for r in rows];raw=[r['raw_goodput'] for r in rows];ckv=[r['CKV_goodput'] for r in rows]
    a.plot(x,raw,'o--',color=RAW,ms=3.4,lw=1.1,label='Native APC');a.plot(x,ckv,'s-',color=CKV,ms=3.4,lw=1.5,label='ContractKV')
    r=rows[1];delta=r['CKV_goodput']-r['raw_goodput'];a.axvline(80,color=GRID,ls=(0,(3,2)),lw=.8)
    a.annotate('',xy=(80,ckv[1]),xytext=(80,raw[1]),arrowprops=dict(arrowstyle='<->',color=CKV,lw=.8))
    a.text(76,.98,f'{ckv[1]:.3f}',ha='right',fontsize=6.7,color=CKV);a.text(76,.28,f'{raw[1]:.3f}',ha='right',fontsize=6.7,color=RAW)
    ci=d['revision_audit']['open_arrival_interval']
    assert abs(float(ci['slo_goodput_delta_rps'])-delta)<1e-9
    a.text(109,.61,f'+{delta:.3f} req/s',ha='center',fontsize=9.0,color=CKV,weight='bold')
    a.text(109,.39,f"95% CI [{float(ci['slo_goodput_delta_ci_low']):.3f}, {float(ci['slo_goodput_delta_ci_high']):.3f}]",ha='center',fontsize=6.1,color=MUTED)
    a.set(xlim=(56,144),ylim=(0,1.7),xticks=x,yticks=[0,.5,1,1.5],xlabel='Offered load (% raw calibration)',ylabel='SLO goodput (req/s)');a.tick_params(labelsize=6.8);a.xaxis.label.set_fontsize(7);a.yaxis.label.set_fontsize(7);a.legend(loc='upper left',fontsize=6.7);gy(a)
    fig.text(.08,.458,'(b) 80-identity density replay',fontsize=8.2,weight='bold')
    dens=[r for r in d['density'] if r['tenants']==80];rr=next(r for r in dens if r['policy']=='D0-native-apc');kk=next(r for r in dens if r['policy']=='D2-full-contractkv')
    fig.text(.55,.417,'+381 free blocks · 71.9% fewer used',ha='center',fontsize=8.0,color=CKV,weight='bold')
    b1=fig.add_axes([.27,.306,.65,.069]);b2=fig.add_axes([.27,.122,.65,.069])
    for ax,values,limit,label,fmt in [(b1,[rr['peak_used_blocks'],kk['peak_used_blocks']],650,'Peak used blocks (pool = 2,386)','{:.0f}'),(b2,[rr['tiered_SLO_goodput'],kk['tiered_SLO_goodput']],14,'Tiered-SLO goodput (req/s)','{:.3f}')]:
        ax.barh([1,0],values,.5,color=[RAW,CKV],ec=INK,lw=.45)
        for yy,v in zip([1,0],values):ax.text(v+limit*.035,yy,fmt.format(v),va='center',fontsize=7.0,weight='bold',color=MUTED if yy else CKV)
        ax.set(yticks=[1,0],yticklabels=['Raw','CKV'],xlim=(0,limit),xlabel=label,xticks=[0,200,400,600] if ax is b1 else [0,4,8,12]);ax.tick_params(labelsize=6.6);ax.xaxis.label.set_fontsize(6.7);gx(ax)
    fig.text(.5,.216,'Same density cells; class-specific SLOs',ha='center',fontsize=6.4,color=MUTED)
    fig.text(.5,.016,'Registered tenants, not concurrent GPU requests',ha='center',fontsize=6.3,color=MUTED)
    save(fig,out,'fig5_service_goodput_and_kv_savings')


def figure6(d,out):
    style();fig=plt.figure(figsize=(3.45,4.3));fig.text(.5,.977,'Frozen deployment workloads',ha='center',va='top',fontsize=6.6,color=MUTED)
    a=fig.add_axes([.18,.600,.77,.277]);b=fig.add_axes([.18,.176,.77,.277])
    xx=[r['sharing_pct'] for r in d['sharing']];vv=[r['TTFT_reduction_pct'] for r in d['sharing']]
    a.axvspan(50,75,fc=PALE,alpha=.8,zorder=0);a.bar(xx,vv,15,color=CKV,ec=INK,lw=.45)
    for x,v in zip(xx,vv):a.text(x,v+(3 if v>=0 else -3),f'{v:.1f}%',ha='center',va='bottom' if v>=0 else 'top',fontsize=6.8,color=CKV,weight='bold')
    a.annotate('Observed transition\n50–75% sharing',xy=(62.5,65),xytext=(17,78),ha='center',color='#087C70',fontsize=6.5,arrowprops=dict(arrowstyle='->',lw=.65,color=REUSE))
    a.axhline(0,color=RAW,lw=.6);a.set(xlim=(-12,112),ylim=(-15,109),xticks=xx,yticks=[0,25,50,75,100],xlabel='Authorized sharing (%)',ylabel='Mean TTFT reduction (%)');title(a,'a','Locality: authorized reuse',pad=7);gy(a)
    for dist,name,color,marker in [('round_robin','Round-robin',RAW,'o'),('zipf','Zipf',CKV,'s')]:
        rows=sorted([r for r in d['residency'] if r['distribution']==dist],key=lambda r:r['active_templates']);x=[r['active_templates'] for r in rows];v=[r['net_TTFT_reduction_pct'] for r in rows]
        b.plot(x,v,marker=marker,color=color,ms=3.6,lw=1.4,label=name)
        for xi,vi in zip(x,v):
            off=-9 if dist=='round_robin' and xi==5 else (3 if dist=='zipf' else -3.5)
            b.text(xi,vi+off,f'{vi:.1f}%',ha='center',va='bottom' if off>0 else 'top',color=color,fontsize=6.8,weight='bold')
    b.annotate('Near-zero benefit\nunder round-robin',xy=(25,.36),xytext=(35,28),ha='center',fontsize=6.6,color=MUTED,arrowprops=dict(arrowstyle='->',lw=.65,color=RAW))
    b.set(xlim=(1,54),ylim=(-15,109),xticks=[5,25,50],yticks=[0,25,50,75,100],xlabel='Active templates',ylabel='Net mean TTFT reduction (%)');title(b,'b','Reuse distance and hot-set skew',pad=7);gy(b)
    for ax in (a,b):ax.tick_params(labelsize=6.8);ax.xaxis.label.set_fontsize(7);ax.yaxis.label.set_fontsize(7)
    b.legend(loc='upper center',bbox_to_anchor=(.5,-.36),ncol=2,fontsize=6.7,columnspacing=1)
    save(fig,out,'fig6_locality_and_residency')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'figures');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    d=json.loads((a.output/'figure_data_v7.json').read_text(encoding='utf-8'))
    d['restored']=json.loads((ROOT/'evidence/restored_evidence.json').read_text(encoding='utf-8'))
    d['revision_audit']=json.loads((ROOT/'evidence/revision_audit_evidence.json').read_text(encoding='utf-8'))
    for draw in (figure2,figure3,figure4,figure5,figure6):draw(d,a.output)
    font=Path(findfont('Arial'))
    record={'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'matplotlib_version':matplotlib.__version__,
            'resolved_font':str(font),'font_file_sha256':hashlib.sha256(font.read_bytes()).hexdigest(),
            'figure_data_sha256':hashlib.sha256((a.output/'figure_data_v7.json').read_bytes()).hexdigest(),
            'restored_evidence_sha256':hashlib.sha256((ROOT/'evidence/restored_evidence.json').read_bytes()).hexdigest(),
            'semantic_colors':{'Raw/reference':RAW,'ContractKV':CKV,'qualified_reuse':REUSE,'certification_cost':COST,'rejected_candidate':REJECT,'D1_frozen_layout':D1},
            'figures':QA,'all_text_inside_canvas':all(not z['text_outside_canvas'] for z in QA),
            'all_text_collision_checks_pass':all(not z['text_bbox_collisions'] for z in QA),
            'paper_exports_include_full_caption':False,'previous_figures_preserved':True}
    (a.output/'render_manifest_v11.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    print(json.dumps({'figures':len(QA),'out_of_bounds':{z['figure']:[x['text'] for x in z['text_outside_canvas']] for z in QA if z['text_outside_canvas']},
                      'collisions':{z['figure']:z['text_bbox_collisions'] for z in QA if z['text_bbox_collisions']}}))


if __name__=='__main__':main()
