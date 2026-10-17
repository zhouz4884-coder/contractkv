"""Revision Fig. 2--6: reuse v5 palette, measured ledgers and editable vectors.

Does not edit Fig. 1, the original figures, or manuscript source files.
Run build_tsc_revision_figure_data_v6.py first.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from matplotlib.text import Text
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('contractkv_v5_style',ROOT/'submission/gen_tsc_figures_v5.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
CKV,SAFE,RISK,VIOLET=old.CKV,old.SAFE,old.RISK,old.VIOLET
NATIVE,NATIVE_LIGHT,INK,MUTED,GRID=old.NATIVE,old.NATIVE_LIGHT,old.INK,old.MUTED,old.GRID
PALE_BLUE,PALE_TEAL=old.PALE_BLUE,old.PALE_TEAL
QA=[]


def style():
    old.set_style(8.0)
    plt.rcParams.update({'axes.titlesize':8.6,'axes.labelsize':7.8,'xtick.labelsize':7.3,
        'ytick.labelsize':7.3,'legend.fontsize':7.1,'axes.linewidth':.7,
        'savefig.bbox':None,'svg.hashsalt':'contractkv-revision-20261017',
        'figure.facecolor':'white','axes.facecolor':'white'})


def title(ax,letter,text):
    ax.set_title(f'({letter})  {text}',loc='left',pad=9,fontweight='bold')


def gy(ax):
    ax.set_axisbelow(True);ax.grid(axis='y',color=GRID,lw=.55)


def gx(ax):
    ax.set_axisbelow(True);ax.grid(axis='x',color=GRID,lw=.55)


def save(fig,out,name):
    fig.canvas.draw();renderer=fig.canvas.get_renderer()
    bounds=fig.bbox
    outside=[]
    for t in fig.findobj(Text):
        if not t.get_visible() or not t.get_text().strip():continue
        b=t.get_window_extent(renderer)
        if b.x0 < -1 or b.y0 < -1 or b.x1 > bounds.width+1 or b.y1 > bounds.height+1:
            outside.append({'text':t.get_text(),'bbox':list(map(float,(b.x0,b.y0,b.x1,b.y1)))})
    files={}
    for ext in ('pdf','svg','png'):
        path=out/(name+'.'+ext)
        kw={'dpi':600} if ext=='png' else {}
        if ext=='pdf':kw['metadata']={'Creator':'ContractKV measured-data figure generator v6','CreationDate':None,'ModDate':None}
        if ext=='svg':kw['metadata']={'Date':None}
        fig.savefig(path,**kw)
        if ext=='svg':
            path.write_bytes(('\n'.join(s.rstrip() for s in path.read_text(encoding='utf-8').splitlines())+'\n').encode())
        files[ext]={'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    QA.append({'figure':name,'width_in':float(fig.get_figwidth()),'height_in':float(fig.get_figheight()),
               'text_outside_canvas':outside,'exports':files})
    plt.close(fig)


def figure2(d,out):
    style();fig=plt.figure(figsize=(7.16,2.85))
    gs=fig.add_gridspec(1,3,width_ratios=[1,1.16,.94],wspace=.48,
                       left=.075,right=.985,bottom=.30,top=.83)
    ax=[fig.add_subplot(gs[0,i]) for i in range(3)]
    labels=['Qwen3\n8B','Mistral\n7B','Llama3.1\n8B'];x=np.arange(3)
    r=d['strict'];v=np.array([z['wall_multiplier'] for z in r])
    err=np.array([[z['wall_multiplier']-z['repeat_min'] for z in r],
                  [z['repeat_max']-z['wall_multiplier'] for z in r]])
    ax[0].bar(x,v,width=.58,color=CKV,edgecolor=INK,lw=.55,zorder=2)
    ax[0].errorbar(x,v,yerr=err,fmt='none',ecolor=INK,capsize=3,lw=.9,zorder=4)
    ax[0].axhline(1,color=NATIVE,lw=.9,ls=(0,(3,2)))
    for i,z in enumerate(r):ax[0].text(i,z['repeat_max']+.06,f"{z['wall_multiplier']:.3f}×",ha='center',weight='bold',color=CKV,fontsize=9.2)
    ax[0].text(.98,.93,'Raw = 1×',transform=ax[0].transAxes,color=MUTED,fontsize=7,ha='right')
    ax[0].set(ylim=(0,1.91),ylabel='Full wall throughput / Raw',xticks=x,xticklabels=labels,yticks=[0,.5,1,1.5])
    title(ax[0],'a','Full wall throughput');gy(ax[0])
    raw=np.array([z['raw_business_prefill_per_repeat']/1e6 for z in r])
    business=np.array([z['CKV_business_prefill_per_repeat']/1e6 for z in r])
    verify=np.array([z['qualification_prefill_per_repeat']/1e6 for z in r])
    w=.32
    ax[1].bar(x-w/2,raw,w,color=NATIVE_LIGHT,edgecolor=NATIVE,lw=.6,label='Raw business')
    ax[1].bar(x+w/2,business,w,color=CKV,edgecolor=INK,lw=.5,label='CKV business')
    ax[1].bar(x+w/2,verify,w,bottom=business,color=RISK,edgecolor=RISK,lw=.6,hatch='///',label='Certification')
    for i in x:
        ax[1].text(i-w/2,raw[i]+.17,f'{raw[i]:.2f}',ha='center',fontsize=7)
        ax[1].text(i+w/2,business[i]+verify[i]+.17,f'{business[i]+verify[i]:.2f}',ha='center',fontsize=7,color=CKV,weight='bold')
    ax[1].set(ylim=(0,8),ylabel='New prefill tokens (millions / run)',xticks=x,xticklabels=labels,yticks=[0,2,4,6,8])
    title(ax[1],'b','Measured prefill work');gy(ax[1])
    handles,legend_labels=ax[1].get_legend_handles_labels()
    fig.legend(handles,legend_labels,loc='upper center',bbox_to_anchor=(.5,.18),ncol=3,
               fontsize=7,handlelength=1.2,columnspacing=2.0,borderpad=.1)
    coverage=[z['compiled_future_pct'] for z in r]
    ax[2].bar(x,coverage,.58,color=SAFE,edgecolor=INK,lw=.5)
    for i,value in enumerate(coverage):ax[2].text(i,value+1.7,f'{value:.2f}%',ha='center',color=SAFE,weight='bold',fontsize=8)
    ax[2].set(ylim=(0,52),ylabel='Compiled future requests (%)',xticks=x,xticklabels=labels,yticks=[0,10,20,30,40,50])
    title(ax[2],'c','Compiled coverage');gy(ax[2])
    fig.text(.5,.08,'Faithful held-out inputs · 16K context · zero tool slack · 3 process pairs/model',ha='center',fontsize=7.4,color=MUTED)
    fig.text(.5,.025,'600 business requests/run; coverage denominator = 1,620 future requests/model. Whiskers: repeat min–max.',ha='center',fontsize=6.9,color=MUTED)
    save(fig,out,'fig2_strict_serving_performance')


def figure3(d,out):
    style();fig=plt.figure(figsize=(7.16,3.08))
    gs=fig.add_gridspec(1,2,width_ratios=[1.06,1],wspace=.30,left=.13,right=.98,bottom=.25,top=.83)
    a=fig.add_subplot(gs[0,0]);b=fig.add_subplot(gs[0,1])
    r=d['strict'];y=np.arange(3)
    positive=np.array([x['raw_positive_compiled_future_pairs'] for x in r])
    zeros=np.array([x['compiled_future_pairs']-x['raw_positive_compiled_future_pairs'] for x in r])
    fallback=np.array([x['raw_L0_future_pairs'] for x in r])
    a.barh(y,positive,height=.54,color=CKV,edgecolor=INK,lw=.5)
    a.barh(y,zeros,left=positive,height=.54,color=PALE_BLUE,edgecolor=CKV,lw=.6,hatch='///')
    a.barh(y,fallback,left=positive+zeros,height=.54,color=NATIVE_LIGHT,edgecolor=NATIVE,lw=.5)
    for i in y:
        a.text(positive[i]/2,i,f'{positive[i]:,}',ha='center',va='center',color='white',fontsize=7.1,weight='bold')
        if zeros[i]:a.text(positive[i]+zeros[i]/2,i,f'{zeros[i]:,}',ha='center',va='center',fontsize=7.1,color=CKV,weight='bold',bbox=dict(fc=PALE_BLUE,ec='none',pad=.25))
        a.text(positive[i]+zeros[i]+fallback[i]/2,i,f'{fallback[i]:,}',ha='center',va='center',fontsize=7.4,color=INK)
    a.set(yticks=y,yticklabels=[x['label'] for x in r],xlim=(0,1620),xticks=[0,540,1080,1620],xlabel='Future requests (1,620 / model)')
    a.invert_yaxis();title(a,'a','Routes and reference task scores');gx(a)
    fig.legend(handles=[Patch(fc=CKV,ec=INK,label='Compiled: raw score > 0'),
                      Patch(fc=PALE_BLUE,ec=CKV,hatch='///',label='Compiled: raw score = 0'),
                      Patch(fc=NATIVE_LIGHT,ec=NATIVE,label='Raw / L0')],
             bbox_to_anchor=(.5,.025),loc='lower center',fontsize=7,ncol=3,
             handlelength=1.2,columnspacing=1.8,borderaxespad=0)
    b.set_axis_off();title(b,'b','Paired free-running evidence')
    b.text(.53,.93,'Observed ID\ndifferences',ha='center',va='top',fontsize=7.3,color=MUTED)
    b.text(.91,.93,'Raw score > 0\nwithin compiled',ha='center',va='top',fontsize=7.3,color=MUTED)
    for yy,x in zip((.64,.35),d['behavior_audits']):
        name='Earlier audit\n50 sources' if x['distinct_sources']==50 else 'Faithful held-out\n6 sources'
        b.text(0,yy,name,va='center',fontsize=7.7)
        b.text(.53,yy,f"{x['ID_divergences']} / {x['compiled_future_pairs']:,}",ha='center',va='center',fontsize=9.5,color=CKV,weight='bold')
        b.text(.91,yy,f"{x['raw_positive_pairs']:,} / {x['compiled_future_pairs']:,}",ha='center',va='center',fontsize=8.0,color=SAFE,weight='bold')
        b.hlines(yy-.15,0,1.04,transform=b.transAxes,color=GRID,lw=.65)
    b.set(xlim=(0,1.05),ylim=(0,1))
    b.text(.52,.02,'Finite observations in frozen behavioral scopes',ha='center',va='bottom',fontsize=7.1,color=MUTED)
    fig.text(.5,.115,'Positive score is not answer correctness; counts retain related tenants and process repeats.',ha='center',fontsize=7.1,color=MUTED)
    save(fig,out,'fig3_observed_generation_behavior')


def figure4(d,out):
    style();fig=plt.figure(figsize=(7.16,3.30))
    gs=fig.add_gridspec(1,3,width_ratios=[1.0,1.00,1.10],wspace=.53,left=.075,right=.98,bottom=.22,top=.84)
    a=fig.add_subplot(gs[0,0]);b=fig.add_subplot(gs[0,1])
    cg=gs[0,2].subgridspec(2,1,hspace=1.05)
    c1=fig.add_subplot(cg[0,0]);c2=fig.add_subplot(cg[1,0])
    r=d['d1_d2'];x=np.arange(2);v=np.array([z['goodput'] for z in r])
    err=[[z['goodput']-z['min'] for z in r],[z['max']-z['goodput'] for z in r]]
    a.bar(x,v,.57,color=[SAFE,CKV],edgecolor=INK,lw=.55)
    a.errorbar(x,v,yerr=err,fmt='none',ecolor=INK,lw=.8,capsize=3)
    for i,z in enumerate(r):a.text(i,z['max']+.065,f"{z['goodput']:.3f}",ha='center',weight='bold',fontsize=9,color=[SAFE,CKV][i])
    a.set(ylim=(0,1.91),ylabel='500-ms SLO goodput (req/s)',xticks=x,xticklabels=['D1\nFrozen safe','D2\nFull CKV'],yticks=[0,.5,1,1.5])
    title(a,'a','Same-engine goodput');gy(a)
    fig.text(.185,.065,'D2: 4 verifier calls / trace\nRegistration charged to full wall',ha='center',fontsize=7.1,color=MUTED,linespacing=1.4)
    b.set_axis_off();title(b,'b','Live PSTP rejection')
    b.text(.01,.88,'Qwen',fontsize=7.3,color=MUTED)
    b.text(.55,.88,'Rejected',ha='center',fontsize=7.3,color=MUTED)
    b.text(.98,.88,'Tokens published\non rejection',ha='center',va='center',fontsize=6.9,color=MUTED)
    for yy,r in zip((.62,.36),d['live_rejection']):
        name='8B' if '14B' not in r['model'] else '14B\nTP=2'
        b.text(.01,yy,name,va='center',fontsize=7.5)
        b.text(.55,yy,f"{r['rejected']} / {r['bad_layouts']}",ha='center',va='center',color=SAFE,weight='bold',fontsize=9.3)
        b.text(.98,yy,str(r['published_rejected_tokens']),ha='center',va='center',color=CKV,weight='bold',fontsize=10.5)
        b.hlines(yy-.13,0,1.06,transform=b.transAxes,color=GRID,lw=.65)
    b.set(xlim=(0,1.06),ylim=(0,1))
    b.text(.53,.045,'Dependency-valid, harmful layouts\n10 cases / model configuration',ha='center',va='bottom',fontsize=7,color=MUTED,linespacing=1.4)
    title(c1,'c','Template amortization')
    for ax,field,lim,xlabel,fmt in [(c1,'calls_per_trace',150,'Verifier calls / trace','{:.0f}'),
                                   (c2,'unhidden_ms_per_future_request',31,'Unhidden cost (ms / future request)','{:.2f}')]:
        values=[z[field] for z in d['granularity']]
        ax.barh([1,0],values,.52,color=[NATIVE_LIGHT,CKV],edgecolor=[NATIVE,INK],lw=.55)
        for yy,value in zip([1,0],values):ax.text(value+lim*.035,yy,fmt.format(value),va='center',fontsize=7.5,weight='bold',color=MUTED if yy else CKV)
        ax.set(yticks=[1,0],yticklabels=['Session','Template'],xlim=(0,lim),xlabel=xlabel)
        ax.xaxis.label.set_fontsize(7.0);ax.tick_params(labelsize=7);gx(ax)
        ax.set_xticks([0,50,100,150] if ax is c1 else [0,10,20,30])
    fig.text(.50,.012,'Original deployment controls: (a) 5 process repeats; (c) 3 repeats × 1,125 future requests.',ha='center',fontsize=7.0,color=MUTED)
    save(fig,out,'fig4_certification_and_template_value')


def figure5(d,out):
    style();fig=plt.figure(figsize=(7.16,2.88))
    gs=fig.add_gridspec(1,2,width_ratios=[1.18,1],wspace=.46,left=.08,right=.975,bottom=.265,top=.82)
    a=fig.add_subplot(gs[0,0]);b=fig.add_subplot(gs[0,1])
    r=d['open_arrival_load'];loads=[x['load_pct'] for x in r];raw=[x['raw_goodput'] for x in r];ckv=[x['CKV_goodput'] for x in r]
    a.fill_between(loads,raw,ckv,color=old.CKV_LIGHT,alpha=.14)
    a.plot(loads,raw,'o--',color=NATIVE,ms=4,lw=1.3,label='Native APC')
    a.plot(loads,ckv,'s-',color=CKV,ms=4,lw=1.7,label='ContractKV')
    a.set(xlim=(56,144),ylim=(0,1.65),xticks=loads,yticks=[0,.5,1,1.5],xlabel='Offered load (% of raw calibration)',ylabel='500-ms SLO goodput (req/s)')
    title(a,'a','Absolute open-arrival goodput');gy(a)
    a.legend(loc='upper left',fontsize=7.2)
    ratio=ckv[1]/raw[1]
    a.annotate(f'80% load: {ratio:.2f}×',xy=(80,ckv[1]),xytext=(93,.48),fontsize=7.2,color=MUTED,
               arrowprops=dict(arrowstyle='-',color=MUTED,lw=.65,connectionstyle='arc3,rad=.12'))
    r=[x for x in d['density'] if x['tenants']==80]
    raw=next(x for x in r if x['policy']=='D0-native-apc');ckv=next(x for x in r if x['policy']=='D2-full-contractkv')
    used=[raw['peak_used_blocks'],ckv['peak_used_blocks']]
    assert used==[530,149] and raw['minimum_free_blocks']==1856 and ckv['minimum_free_blocks']==2237
    b.barh([1,0],used,.52,color=[NATIVE,CKV],edgecolor=INK,lw=.55)
    for yy,value in zip([1,0],used):b.text(value+13,yy,f'{value:.0f}',va='center',fontsize=10,weight='bold',color=CKV if yy==0 else MUTED)
    b.set(xlim=(0,650),ylim=(-.65,1.65),yticks=[1,0],yticklabels=['Native APC','ContractKV'],xticks=[0,150,300,450,600],xlabel='Peak allocator-used KV blocks')
    title(b,'b','Physical KV use at 80 identities');gx(b)
    b.text(.5,.91,f"{100*(1-used[1]/used[0]):.1f}% fewer used blocks",transform=b.transAxes,ha='center',fontsize=10,color=CKV,weight='bold')
    b.text(.5,.02,'Pool: 2,386 blocks; free: 1,856 → 2,237',transform=b.transAxes,ha='center',fontsize=7,color=MUTED)
    fig.text(.5,.075,'Original deployment-template protocols · three process repeats · allocator-observed physical blocks',ha='center',fontsize=7,color=MUTED)
    fig.text(.5,.025,'80 registered tenant identities ≠ 80 simultaneously executing GPU requests.',ha='center',fontsize=7.3,color=MUTED)
    save(fig,out,'fig5_service_scale_and_physical_reuse')


def figure6(d,out):
    style();fig=plt.figure(figsize=(7.16,3.05))
    gs=fig.add_gridspec(1,2,width_ratios=[1,1],wspace=.35,left=.08,right=.975,bottom=.285,top=.83)
    a=fig.add_subplot(gs[0,0]);b=fig.add_subplot(gs[0,1])
    x=[r['sharing_pct'] for r in d['sharing']];v=[r['TTFT_reduction_pct'] for r in d['sharing']]
    a.bar(x,v,width=15,color=[RISK if z<0 else CKV for z in v],edgecolor=INK,lw=.55)
    for xx,z in zip(x,v):a.text(xx,z+(2.8 if z>=0 else -3),f'{z:.1f}%',ha='center',va='bottom' if z>=0 else 'top',fontsize=7.5,weight='bold',color=RISK if z<0 else CKV)
    a.axhline(0,color=NATIVE,lw=.7)
    a.set(xlim=(-12,112),ylim=(-13,108),xticks=x,yticks=[0,25,50,75,100],xlabel='Authorized sharing (%)',ylabel='Mean TTFT reduction (%)')
    title(a,'a','Authorized reuse density');gy(a)
    for distribution,label,color,marker in [('round_robin','Round-robin',NATIVE,'o'),('zipf','Zipf',CKV,'s')]:
        r=sorted([z for z in d['residency'] if z['distribution']==distribution],key=lambda z:z['active_templates'])
        xx=[z['active_templates'] for z in r];vv=[z['net_TTFT_reduction_pct'] for z in r]
        b.plot(xx,vv,marker=marker,color=color,ms=4.5,lw=1.7,label=label)
        for xi,z in zip(xx,vv):
            delta=-8 if distribution=='round_robin' and xi==5 else (3 if distribution=='zipf' else -3.5)
            b.text(xi,z+delta,f'{z:.1f}%',ha='center',va='bottom' if delta>0 else 'top',fontsize=7.4,color=color,weight='bold')
    b.set(xlim=(1,54),ylim=(-13,108),xticks=[5,25,50],yticks=[0,25,50,75,100],xlabel='Active templates',ylabel='Net mean TTFT reduction (%)')
    title(b,'b','Working-set residency');gy(b)
    b.legend(loc='upper center',bbox_to_anchor=(.5,-.29),ncol=2,fontsize=7.2,columnspacing=1.5)
    fig.text(.28,.095,'40 registered identities; paired native baseline.',ha='center',fontsize=7.0,color=MUTED)
    fig.text(.5,.02,'Original deployment protocols: qualification authorizes reuse; physical residency enables the savings.',ha='center',fontsize=7.2,color=MUTED)
    save(fig,out,'fig6_operating_region')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'Paper/figures/revision_20261017');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    d=json.loads((a.output/'figure_data_v6.json').read_text(encoding='utf-8'))
    for draw in (figure2,figure3,figure4,figure5,figure6):draw(d,a.output)
    font=Path(font_manager.findfont('Arial'))
    record={'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'matplotlib_version':matplotlib.__version__,'resolved_font':str(font),
            'font_file_sha256':hashlib.sha256(font.read_bytes()).hexdigest(),
            'figure_data_sha256':hashlib.sha256((a.output/'figure_data_v6.json').read_bytes()).hexdigest(),
            'figures':QA,'all_text_inside_canvas':all(not x['text_outside_canvas'] for x in QA),
            'manual_visual_QA_required':True,'original_figures_and_Fig1_unchanged':True}
    (a.output/'render_manifest_v6.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    print(json.dumps({'figures':len(QA),'out_of_bounds':{x['figure']:[z['text'] for z in x['text_outside_canvas']] for x in QA if x['text_outside_canvas']}}))


if __name__=='__main__':main()
