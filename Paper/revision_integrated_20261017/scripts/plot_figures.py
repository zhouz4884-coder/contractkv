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
        'svg.hashsalt':'contractkv-v8-20261017','figure.facecolor':'white','axes.facecolor':'white'})


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
        if ext=='pdf':kw['metadata']={'Creator':'ContractKV measured-data figures v8','CreationDate':None,'ModDate':None}
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
    style();fig=plt.figure(figsize=(7.16,3.30))
    tag(fig,'Frozen behavioral scopes · task-level coverage and measured output-ID fidelity')
    a=fig.add_axes([.145,.44,.325,.365]);b=fig.add_axes([.60,.44,.375,.365])
    values=np.array([[x['coverage_pct'] for x in z['family_coverage']] for z in d['strict']])
    cmap=LinearSegmentedColormap.from_list('qualified_reuse',['#EFF8F5','#087C70'])
    for i,z in enumerate(d['strict']):
        for j,r in enumerate(z['family_coverage']):
            inherited=r['inherited_L0'];color='#EDF0F2' if inherited else cmap(values[i,j]/70)
            a.add_patch(Rectangle((j-.5,i-.5),1,1,fc=color,ec='white',lw=2,
                                 hatch='///' if inherited else None))
            if inherited:
                a.add_patch(Rectangle((j-.5,i-.5),1,1,fc='none',ec='#B6BEC5',lw=.5,hatch='///'))
                a.text(j,i,'Inherited L0\n0 / 810',ha='center',va='center',fontsize=7.8,color=MUTED,
                       bbox=dict(fc='#EDF0F2',ec='none',pad=.3))
            else:
                a.text(j,i,f"{r['coverage_pct']:.1f}%\n{r['compiled_pairs']} / 810",ha='center',va='center',
                       fontsize=8.4,color='white' if values[i,j]>50 else INK,weight='bold',linespacing=1.5)
    a.set(xlim=(-.5,1.5),ylim=(2.5,-.5),xticks=[0,1],xticklabels=['HotpotQA','RepoBench'],
          yticks=[0,1,2],yticklabels=[z['label'] for z in d['strict']])
    a.tick_params(length=0)
    for spine in a.spines.values():spine.set_visible(False)
    title(a,'a','Task-level compiled coverage')
    a.text(.5,-.18,'810 future pairs / model / task family',transform=a.transAxes,ha='center',fontsize=6.8,color=MUTED)
    b.set_axis_off();title(b,'b','Observed output-ID differences')
    for yy,r in zip((.84,.64),d['behavior_audits']):
        label='Earlier audit (50 sources)' if r['distinct_sources']==50 else 'Faithful held-out (6 sources)'
        b.text(0,yy,label,va='center',fontsize=7.3)
        b.text(1,yy,f"{r['ID_divergences']} / {r['compiled_future_pairs']:,}",ha='right',va='center',color=CKV,weight='bold',fontsize=9)
    b.axhline(.52,color=GRID,lw=.65)
    b.text(0,.43,'Compiled subset: raw reference score > 0',fontsize=7.1,color=MUTED)
    for yy,name,r in zip((.30,.16,.02),('Qwen','Mistral','Llama'),d['strict']):
        ratio=r['raw_positive_compiled_future_pairs']/r['compiled_future_pairs']
        b.text(0,yy,name,fontsize=7.1,va='center')
        b.add_patch(Rectangle((.29,yy-.026),.37,.052,fc='#E2E8EB',ec='none'))
        b.add_patch(Rectangle((.29,yy-.026),.37*ratio,.052,fc=REUSE,ec='none'))
        b.text(1,yy,f"{r['raw_positive_compiled_future_pairs']} / {r['compiled_future_pairs']}",ha='right',va='center',fontsize=7.3,color=REUSE,weight='bold')
    b.set(xlim=(0,1),ylim=(-.035,1))
    c=fig.add_axes([.065,.045,.91,.235]);c.set_axis_off()
    t=d['measured_trace'];title(c,'c','One logged Qwen / HotpotQA sequence: t0 → t3',pad=4)
    labels=[('Raw witness, t0','7 output IDs',RAW),('Verification PASS','same query scope',REUSE),
            ('PSTP COMMITTED',f"{t['committed_full_blocks']} candidate blocks",CKV),
            ('Later answer, t3','same 7 output IDs',REUSE)]
    for i,(first,second,color) in enumerate(labels):
        x=.01+.25*i
        c.add_patch(Rectangle((x,.19),.215,.52,fc='white',ec=color,lw=.8))
        c.text(x+.1075,.45,first+'\n'+second,ha='center',va='center',fontsize=7.1,linespacing=1.5,color=INK)
        if i<3:c.annotate('',xy=(x+.25,.45),xytext=(x+.22,.45),arrowprops=dict(arrowstyle='->',lw=.8,color=MUTED))
    c.text(.5,.015,f"Later native hit: {t['later_native_hit_tokens']:,} tokens · exact records in artifact",ha='center',fontsize=6.7,color=MUTED)
    save(fig,out,'fig3_coverage_and_fidelity')


def figure4(d,out):
    style();fig=plt.figure(figsize=(7.16,3.10));tag(fig,'Deployment-template controls · certificate granularity, live rejection, and same-engine service')
    fig.text(.075,.875,'(a) Certificate amortization',weight='bold',fontsize=8.5)
    a1=fig.add_axes([.135,.61,.27,.17]);a2=fig.add_axes([.135,.205,.27,.17])
    for ax,field,lim,label,format_,headline in [
        (a1,'calls_per_trace',150,'Verifier calls / trace','{:.0f}','25× fewer calls'),
        (a2,'unhidden_ms_per_future_request',31,'Unhidden ms / future request','{:.2f}','7.7× lower cost')]:
        values=[z[field] for z in d['granularity']]
        ax.barh([1,0],values,.52,color=[LIGHT,CKV],ec=[RAW,INK],lw=.5)
        for y,value in zip([1,0],values):ax.text(value+lim*.035,y,format_.format(value),va='center',fontsize=7.5,color=CKV if y==0 else MUTED,weight='bold')
        ax.set(yticks=[1,0],yticklabels=['Session','Template'],xlim=(0,lim),xlabel=label)
        ax.set_xticks([0,50,100,150] if ax is a1 else [0,10,20,30]);gx(ax)
        ax.text(0,1.15,headline,transform=ax.transAxes,fontsize=13.5 if ax is a1 else 12.3,color=CKV,weight='bold')
    b=fig.add_axes([.50,.205,.19,.60]);b.set_axis_off();title(b,'b','Fail-closed promotion')
    states=[(.77,.15,'Harmful candidate',RAW),(.49,.15,'Certification FAIL',REJECT),
            (.16,.22,'0 rejected-candidate\nKV blocks promoted',CKV)]
    for yy,hh,label,color in states:
        b.add_patch(Rectangle((.01,yy),.98,hh,fc='white',ec=color,lw=.8))
        b.text(.5,yy+hh/2,label,ha='center',va='center',fontsize=7.2,color=color,weight='bold' if color==REJECT else 'normal')
    for high,low in ((.77,.64),(.49,.38)):
        b.annotate('',xy=(.5,low+.01),xytext=(.5,high-.01),arrowprops=dict(arrowstyle='->',color=MUTED,lw=.8))
    b.text(.5,.005,'8B: 10/10 rejected\n14B TP2: 10/10 rejected',ha='center',va='bottom',fontsize=6.9,color=MUTED,linespacing=1.4)
    c=fig.add_axes([.80,.32,.175,.30]);title(c,'c','Goodput under\ngovernance',pad=43)
    fig.text(.8875,.76,f"{d['governance_goodput_retained_pct']:.1f}%",ha='center',color=CKV,weight='bold',fontsize=10.5)
    fig.text(.8875,.70,'D1 goodput retained',ha='center',fontsize=7.1,color=MUTED)
    values=[z['goodput'] for z in d['d1_d2']]
    c.barh([1,0],values,.46,color=[D1,CKV],ec=INK,lw=.5)
    for yy,r in zip([1,0],d['d1_d2']):
        c.errorbar(r['goodput'],yy,xerr=[[r['goodput']-r['min']],[r['max']-r['goodput']]],fmt='none',ecolor=INK,lw=.8,capsize=2)
        c.text(.63,yy,f"{r['goodput']:.3f}",va='center',ha='center',fontsize=7.4,color='white' if yy==0 else INK,weight='bold')
    c.set(yticks=[1,0],yticklabels=['D1','D2'],xlim=(0,1.85),xticks=[0,.8,1.6],xlabel='500-ms SLO req/s');gx(c)
    fig.text(.8875,.15,'Whiskers: 5-repeat min–max',ha='center',fontsize=6.3,color=MUTED)
    fig.text(.8875,.055,'Verifier calls / trace\nD1: 0 · D2: 4',ha='center',fontsize=6.9,color=COST,linespacing=1.4)
    save(fig,out,'fig4_transaction_and_amortization')


def figure5(d,out):
    style();fig=plt.figure(figsize=(7.16,2.95));tag(fig,'Deployment-template evaluation · open-arrival and density studies shown separately')
    a=fig.add_axes([.08,.205,.42,.61]);title(a,'a','Open arrival: 500-ms SLO')
    rows=d['open_arrival_load'];x=[z['load_pct'] for z in rows];raw=[z['raw_goodput'] for z in rows];ckv=[z['CKV_goodput'] for z in rows]
    a.plot(x,raw,'o--',color=RAW,ms=4,lw=1.2,label='Native APC')
    a.plot(x,ckv,'s-',color=CKV,ms=4,lw=1.7,label='ContractKV')
    r=rows[1];delta=r['CKV_goodput']-r['raw_goodput'];ratio=r['CKV_goodput']/r['raw_goodput']
    a.axvline(80,color=GRID,ls=(0,(3,2)),lw=.9,zorder=0)
    a.scatter([80,80],[raw[1],ckv[1]],c=[RAW,CKV],s=40,ec='white',lw=.7,zorder=4)
    a.annotate('',xy=(80,ckv[1]),xytext=(80,raw[1]),arrowprops=dict(arrowstyle='<->',color=CKV,lw=.9))
    a.text(76,.995,f'CKV {ckv[1]:.3f}',ha='right',color=CKV,fontsize=7.0)
    a.text(76,.265,f'Raw {raw[1]:.3f}',ha='right',color=RAW,fontsize=7.0)
    a.text(105,.57,f'+{delta:.3f}',ha='center',color=CKV,fontsize=12.0,weight='bold')
    a.text(105,.44,'SLO-compliant req/s',ha='center',color=CKV,fontsize=7.2)
    a.text(105,.32,f'{ratio:.2f}× at 80% load',ha='center',color=MUTED,fontsize=7)
    a.set(xlim=(56,144),ylim=(0,1.7),xticks=x,yticks=[0,.5,1,1.5],xlabel='Offered load (% raw calibration)',ylabel='SLO goodput (req/s)');gy(a)
    a.legend(loc='upper left',fontsize=7.1)
    fig.text(.66,.875,'(b) 80-identity density replay',fontsize=8.4,weight='bold')
    dens=[z for z in d['density'] if z['tenants']==80]
    rr=next(z for z in dens if z['policy']=='D0-native-apc');kk=next(z for z in dens if z['policy']=='D2-full-contractkv')
    headroom=kk['minimum_free_blocks']-rr['minimum_free_blocks']
    fig.text(.81,.795,f'+{headroom:.0f} free blocks',ha='center',color=CKV,fontsize=11,weight='bold')
    fig.text(.81,.748,f"{100*(1-kk['peak_used_blocks']/rr['peak_used_blocks']):.1f}% fewer used · pool = 2,386",ha='center',color=MUTED,fontsize=7.0)
    b1=fig.add_axes([.66,.56,.31,.15]);b2=fig.add_axes([.66,.205,.31,.16])
    for ax,values,limit,label,fmt in [
        (b1,[rr['peak_used_blocks'],kk['peak_used_blocks']],650,'Peak used KV blocks','{:.0f}'),
        (b2,[rr['tiered_SLO_goodput'],kk['tiered_SLO_goodput']],14,'Tiered-SLO goodput (req/s)','{:.3f}')]:
        ax.barh([1,0],values,.5,color=[RAW,CKV],ec=INK,lw=.5)
        for yy,v in zip([1,0],values):ax.text(v+limit*.035,yy,fmt.format(v),va='center',fontsize=7.3,weight='bold',color=MUTED if yy else CKV)
        ax.set(yticks=[1,0],yticklabels=['Raw','CKV'],xlim=(0,limit),xlabel=label)
        ax.xaxis.label.set_fontsize(7);gx(ax)
        ax.set_xticks([0,200,400,600] if ax is b1 else [0,4,8,12])
    b2.text(.5,1.18,'Same density cells; class-specific SLOs',transform=b2.transAxes,ha='center',fontsize=6.9,color=MUTED)
    fig.text(.81,.025,'Registered tenants, not concurrent GPU requests',ha='center',fontsize=6.4,color=MUTED)
    save(fig,out,'fig5_service_goodput_and_kv_savings')


def figure6(d,out):
    style();fig=plt.figure(figsize=(7.16,2.75));tag(fig,'Frozen deployment workloads · observed locality transition and access-pattern sensitivity')
    gs=fig.add_gridspec(1,2,left=.08,right=.975,bottom=.24,top=.80,wspace=.34)
    a=fig.add_subplot(gs[0,0]);b=fig.add_subplot(gs[0,1])
    x=[z['sharing_pct'] for z in d['sharing']];v=[z['TTFT_reduction_pct'] for z in d['sharing']]
    a.axvspan(50,75,fc=PALE,alpha=.8,zorder=0)
    a.bar(x,v,15,color=CKV,ec=INK,lw=.5)
    for xx,z in zip(x,v):a.text(xx,z+(2.8 if z>=0 else -3),f'{z:.1f}%',ha='center',va='bottom' if z>=0 else 'top',color=CKV,fontsize=7.2,weight='bold')
    a.annotate('Observed transition\n50–75% sharing',xy=(62.5,65),xytext=(18,79),ha='center',
               color='#087C70',fontsize=7.0,linespacing=1.3,
               arrowprops=dict(arrowstyle='->',lw=.7,color=REUSE))
    a.axhline(0,color=RAW,lw=.7)
    a.set(xlim=(-12,112),ylim=(-13,108),xticks=x,yticks=[0,25,50,75,100],xlabel='Authorized sharing (%)',ylabel='Mean TTFT reduction (%)')
    title(a,'a','Locality: authorized reuse');gy(a)
    for distribution,name,color,marker in [('round_robin','Round-robin',RAW,'o'),('zipf','Zipf',CKV,'s')]:
        rows=sorted([z for z in d['residency'] if z['distribution']==distribution],key=lambda z:z['active_templates'])
        xx=[z['active_templates'] for z in rows];vv=[z['net_TTFT_reduction_pct'] for z in rows]
        b.plot(xx,vv,marker=marker,color=color,ms=4.3,lw=1.6,label=name)
        for xi,z in zip(xx,vv):
            off=-8 if distribution=='round_robin' and xi==5 else (3 if distribution=='zipf' else -3.5)
            b.text(xi,z+off,f'{z:.1f}%',ha='center',va='bottom' if off>0 else 'top',color=color,fontsize=7.2,weight='bold')
    b.annotate('Near-zero benefit\nunder round-robin',xy=(25,.36),xytext=(35,27),fontsize=7.1,color=MUTED,
               ha='center',arrowprops=dict(arrowstyle='->',color=RAW,lw=.7))
    b.set(xlim=(1,54),ylim=(-13,108),xticks=[5,25,50],yticks=[0,25,50,75,100],xlabel='Active templates',ylabel='Net mean TTFT reduction (%)')
    title(b,'b','Reuse distance and hot-set skew');gy(b)
    b.legend(loc='upper center',bbox_to_anchor=(.5,-.27),ncol=2,fontsize=7.0,columnspacing=1.5)
    save(fig,out,'fig6_locality_and_residency')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'figures');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    d=json.loads((a.output/'figure_data_v7.json').read_text(encoding='utf-8'))
    for draw in (figure2,figure3,figure4,figure5,figure6):draw(d,a.output)
    font=Path(findfont('Arial'))
    record={'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'matplotlib_version':matplotlib.__version__,
            'resolved_font':str(font),'font_file_sha256':hashlib.sha256(font.read_bytes()).hexdigest(),
            'figure_data_sha256':hashlib.sha256((a.output/'figure_data_v7.json').read_bytes()).hexdigest(),
            'semantic_colors':{'Raw/reference':RAW,'ContractKV':CKV,'qualified_reuse':REUSE,'certification_cost':COST,'rejected_candidate':REJECT,'D1_frozen_layout':D1},
            'figures':QA,'all_text_inside_canvas':all(not z['text_outside_canvas'] for z in QA),
            'all_text_collision_checks_pass':all(not z['text_bbox_collisions'] for z in QA),
            'paper_exports_include_full_caption':False,'previous_figures_preserved':True}
    (a.output/'render_manifest_v8.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    print(json.dumps({'figures':len(QA),'out_of_bounds':{z['figure']:[x['text'] for x in z['text_outside_canvas']] for z in QA if z['text_outside_canvas']},
                      'collisions':{z['figure']:z['text_bbox_collisions'] for z in QA if z['text_bbox_collisions']}}))


if __name__=='__main__':main()
