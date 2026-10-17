"""Package paper-ready v7 graphics, separate captions and provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import fitz
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
FIGURES=[('fig2_full_cost_benefits','Fig. 2. Full-Cost Benefits of Query-Scoped KV Reuse'),
 ('fig3_coverage_and_fidelity','Fig. 3. Qualified Coverage and Free-Running Fidelity'),
 ('fig4_transaction_and_amortization','Fig. 4. Transactional Enforcement and Certificate Amortization'),
 ('fig5_service_goodput_and_kv_savings','Fig. 5. Service Goodput and Physical KV Savings'),
 ('fig6_locality_and_residency','Fig. 6. How Locality and Residency Shape KV Reuse')]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,s):p.write_bytes((s.rstrip()+'\n').encode('utf-8'))
def table(head,values):return '\n'.join(['| '+' | '.join(head)+' |','| '+' | '.join(['---']*len(head))+' |']+['| '+' | '.join(map(str,x))+' |' for x in values])


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'Paper/figures/revision_20261017_v7');a=p.parse_args();out=a.output
    d=json.loads((out/'figure_data_v7.json').read_text(encoding='utf-8'))
    manifest=json.loads((out/'source_manifest_v7.json').read_text(encoding='utf-8'))
    render=json.loads((out/'render_manifest_v7.json').read_text())
    assert render['all_text_inside_canvas'] and render['all_text_collision_checks_pass']
    captions=[
      ('Full-cost benefits on six source-disjoint HotpotQA/RepoBench sources, three models and three paired process repetitions/model. '
       'The strict query-scoped raw-witness protocol uses faithful 16K inputs and zero tool slack. '
       '(a) Bars normalize aggregate full service throughput to raw over three process pairs; individual ratios and min-max are retained in the supporting tables. '
       'Service wall charges initial business, planning, successful/failed qualification and synchronous waits, scoring and logging. '
       '(b) ContractKV totals include business and certification prefill; annotations report net count reduction and added certification work. '
       'Counts are initial scheduler prompt-minus-hit observations per 600-business-request run. '
       '(c) Mean readiness TTFT uses the frozen two-request wave clock over future requests. Process means, source-cluster intervals and tail costs are retained in the supporting tables.'),
      ('(a) Task-level compiled coverage; each cell contains 810 future pairs/model/family. Hatched RepoBench cells inherit a development-frozen L0 policy and are not GPU-certification failures. '
       '(b) The earlier 50-source audit and six-source faithful validation observed 0/2,442 and 0/1,296 compiled output-ID differences. '
       'The lower panel reports raw-positive scorer credit within the faithful compiled subset, not a common accuracy measure. '
       '(c) One logged Qwen3-8B/HotpotQA doc69 sequence: an actual t0 witness, PASS/COMMITTED reply reporting 888 candidate blocks, and a t3 answer with identical seven output IDs plus native prefix reuse. '
       'Exact records and line identities are supplied; a standalone BlockStored event is not claimed.'),
      ('(a) The fixed-layout deployment certificate-granularity ablation reduces calls from 125 to 5 per 1,125-future-request trace (25-fold) and unhidden cost from 25.05 to 3.24 ms/request (7.7-fold); three process repetitions, independent axes. '
       '(b) Live Qwen 8B and 14B TP2 probes each reject 10/10 harmful dependency-valid layouts. Zero promotion applies to rejected compiled candidate state; native raw fallback caching remains separate. '
       '(c) A distinct five-process same-engine comparison reports D1/D2 goodput of 1.472/1.428 req/s, giving 97.0% retained mean goodput with four D2 verifier calls/trace. '
       'Whiskers are process min-max, not confidence intervals or a non-inferiority guarantee.'),
      ('Distinct original deployment-template studies. (a) The open-arrival workload reports absolute 500-ms SLO goodput. '
       'At 80% load, native APC and ContractKV achieve 0.173/0.831 req/s: +0.658 req/s and a 4.81x measured-point ratio. '
       '(b) In the same 80-identity density cells, peak allocator-used blocks fall 530 to 149 (71.9%) and minimum free blocks rise 381 within a 2,386-block pool. '
       'Those density cells also report 1.152/11.033 req/s under class-specific 750/1,500/3,000-ms SLOs in wave replay. '
       'The two SLO protocols stay separate. Registered identities are not simultaneous GPU requests, and these data do not isolate headroom as the sole cause of throughput improvement.'),
      ('(a) In the frozen 40-identity sharing sweep, the pale band marks the observed 50-75% sharing interval across which mean TTFT benefit rises; it is not a universal threshold. '
       'The zero-sharing -3.2% point is retained. (b) Round-robin and Zipf patterns over 5, 25 and 50 templates expose sensitivity to reuse distance and hot-set skew. '
       'The axis measures net mean TTFT reduction, not a directly observed residency fraction. Prefix-hit statistics are supplied separately. '
       'These observations distinguish reuse qualification from continued physical availability of KV state; no new eviction timeline or policy is inferred from the curves.')]
    text=['# Figure captions — version 7','',
          'The individual PDF/SVG/PNG files contain compact graphics only. This document supplies separate LaTeX-ready caption drafts. Fig. 1 and manuscript source are unchanged.','']
    for (stem,title),caption in zip(FIGURES,captions):text+=['## '+title,'',caption,'',f'[PDF]({stem}.pdf) · [SVG]({stem}.svg) · [PNG]({stem}.png)','']
    write(out/'captions_v7.md','\n'.join(text))
    old=(ROOT/'Paper/figures/revision_20261017/supporting_tables_v6.md').read_text(encoding='utf-8')
    extra=['','## H. Task-family coverage (faithful primary validation)','',
        table(['Model','Family','Compiled future pairs','Coverage','Inherited family L0'],[
            [z['label'],r['family'],f"{r['compiled_pairs']} / {r['future_pairs']}",f"{r['coverage_pct']:.2f}%",r['inherited_L0']]
            for z in d['strict'] for r in z['family_coverage']]),
        '', '## I. Mean readiness timing (same primary validation)','',
        table(['Model','Raw mean (ms)','CKV mean (ms)','Mean reduction','Source/repeat 95% interval for reduction (%)'],[
            [r['label'],f"{r['raw_ready_mean_ms']:.2f}",f"{r['CKV_ready_mean_ms']:.2f}",f"{r['ready_mean_reduction_pct']:.2f}%",
             f"[{r['ready_mean_reduction_CI95_low']:.3f}, {r['ready_mean_reduction_CI95_high']:.3f}]"] for r in d['strict']]),
        '', '## J. Earlier-audit raw-positive count recheck by metric family','',
        'The 2,442/2,442 positive-score count is reproduced from every compiled pair. It combines distinct scorer-credit definitions and is not a unified correctness or accuracy claim.','',
        table(['Task family','Study','Scorer-credit group','Compiled future pairs','Raw score >0','Raw score =0'],[
            [r['family'],r['study'],r['scorer_group'],r['compiled_future_pairs'],r['raw_score_positive'],r['raw_score_zero']]
            for r in d['earlier_positive_score_audit']]),
        '', '## K. Logged sequence included in Fig. 3(c)','',
        'The case selector takes the first issued certificate in file order and its first matching witness/future; equality and publication checks then validate that fixed selection.','',
        table(['Field','Observed value'],[[key,str(d['measured_trace'][key])] for key in ('source_group','query_scope','raw_request_id',
            'verification_request_id','future_request_id','raw_turn','future_turn','output_ID_count','output_token_ids','output_ID_SHA256',
            'verification_decision','txn_state','committed_full_blocks','committed_tokens','later_native_hit_tokens','certificate_hash')]),
        '', 'Exact selected records, per-line hashes, upstream full-file SHA256 and line indices are in `trace_log_excerpt_v7.json`. The compact source bundle carries the selected records; full primary archives support independent re-extraction.','',
        '## L. Density block/goodput values come from the same cells','',
        table(['Policy','Cell','Repeat','SLO goodput','Peak used blocks','Minimum free blocks'],[
            [group['policy'],r['cell_id'],r['repeat'],r['slo_compliant_goodput_rps'],r['peak_used_gpu_blocks'],r['minimum_free_gpu_blocks']]
            for group in d['density80_same_cell_audit'] for r in group['rows']]),
        '', 'This density experiment is a bounded-concurrency wave replay with tiered SLOs. It is distinct from the fixed open-arrival 500-ms curve.','',
        '## M. Access-pattern prefix-hit statistics','',
        table(['Templates','Access pattern','Net mean TTFT reduction','CKV prefix-hit ratio'],[
            [r['active_templates'],r['distribution'],f"{r['net_TTFT_reduction_pct']:.3f}%",f"{r['CKV_prefix_hit_pct']:.3f}%"] for r in d['residency']]),
        '', '## N. Process-repeat statistics (markers omitted from Fig. 2)','',
        table(['Model','Aggregate throughput / Raw','Repeat 1','Repeat 2','Repeat 3','Min-max'],[
            [r['label'],f"{r['wall_multiplier']:.6f}"] +
            [f'{v:.6f}' for v in r['repeat_wall_multipliers']] +
            [f"[{r['repeat_min']:.6f}, {r['repeat_max']:.6f}]"] for r in d['strict']]),
        '', table(['Model','Policy','Repeat 1 mean readiness (ms)','Repeat 2 (ms)','Repeat 3 (ms)'],[
            [r['label'],policy] + [f'{v:.2f}' for v in r['repeat_ready_means_ms'][policy]]
            for r in d['strict'] for policy in ('raw-order','risk-tail')])]
    write(out/'supporting_tables_v7.md',old+'\n'+'\n'.join(extra))
    review=fitz.open();font=render['resolved_font'];fontname='ReviewArial'
    for (stem,title),caption in zip(FIGURES,captions):
        page=review.new_page(width=612,height=448);page.insert_font(fontname=fontname,fontfile=font)
        assert page.insert_textbox(fitz.Rect(24,12,588,44),title,fontname=fontname,fontsize=12,color=(.08,.20,.32))>=0
        with fitz.open(out/(stem+'.pdf')) as src:page.show_pdf_page(fitz.Rect(24,48,588,320),src,0,keep_proportion=True)
        assert page.insert_textbox(fitz.Rect(24,330,588,438),caption,fontname=fontname,fontsize=8.1,lineheight=1.25,color=(.12,.14,.16))>=0
    review.set_metadata({'title':'ContractKV figures 2–6, information-focused revision v7','subject':'Review copy with separate captions'})
    review.save(out/'ContractKV_Fig2-6_review_v7.pdf',garbage=4,deflate=True)
    cards=[];face=ImageFont.truetype(font,23)
    for stem,title in FIGURES:
        image=Image.open(out/(stem+'.png')).convert('RGB');image.thumbnail((1050,500))
        card=Image.new('RGB',(1110,570),'white');draw=ImageDraw.Draw(card)
        draw.text((18,12),title[:76],font=face,fill='#15599A')
        card.paste(image,((1110-image.width)//2,58+(500-image.height)//2));cards.append(card)
    sheet=Image.new('RGB',(2220,1710),'#E9EEF2')
    for i,card in enumerate(cards):sheet.paste(card,((i%2)*1110,(i//2)*570))
    ImageDraw.Draw(sheet).text((1140,1190),'Measured protocols\nCompact vector graphics\nSeparate captions + source data',font=ImageFont.truetype(font,29),fill='#15599A',spacing=16)
    sheet.save(out/'all_figures_preview_v7.png')
    source_paths=[ROOT/x['path'] for x in manifest['sources']]+[ROOT/'submission'/name for name in (
        'extract_tsc_revision_trace_v7.py','build_tsc_revision_figure_data_v7.py','gen_tsc_figures_v7.py','package_tsc_revision_figures_v7.py')]
    source_paths=list(dict.fromkeys(source_paths))
    assert all(sha(ROOT/x['path'])==x['sha256'] for x in manifest['sources'])
    with zipfile.ZipFile(out/'plot_sources_v7.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in source_paths:z.write(f,f.relative_to(ROOT).as_posix())
    bundle={'archive':'plot_sources_v7.zip','sha256':sha(out/'plot_sources_v7.zip'),
            'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in source_paths]}
    write(out/'plot_sources_manifest_v7.json',json.dumps(bundle,indent=2))
    expected=[['1.619','1.109','1.070','45.4%','43.9%','0.074M'],
              ['63.7%','20.7%','42.2%','33.3%','Inherited L0','0 / 2,442','0 / 1,296','888','14,240'],
              ['25×','7.7×','97.0%','125','25.05','3.24','1.472','1.428','KV blocks promoted'],
              ['+0.658','0.173','0.831','4.81','381','71.9%','530','149','2,386','1.152','11.033'],
              ['-3.2%','93.3%','84.6%','73.4%','Observed transition']]
    qa=[]
    for (stem,_),texts in zip(FIGURES,expected):
        with fitz.open(out/(stem+'.pdf')) as pdf:
            page=pdf[0];actual=' '.join(page.get_text().split())
            assert all(x in actual for x in texts),(stem,[x for x in texts if x not in actual])
            fonts=pdf.get_page_fonts(0,full=True);assert all(x[2]!='Type3' and pdf.extract_font(x[0])[3] for x in fonts)
            assert not page.get_images()
            nodes=[x.tag.rsplit('}',1)[-1] for x in ET.parse(out/(stem+'.svg')).getroot().iter()]
            assert 'image' not in nodes and nodes.count('text')>0
            image=Image.open(out/(stem+'.png'));assert image.width==4296
            qa.append({'figure':stem,'key_values_checked_in_actual_PDF_text':texts,'PDF_fonts_embedded':True,
                'Type3_fonts':0,'raster_nodes_in_PDF_or_SVG':0,'SVG_editable_text_nodes':nodes.count('text'),
                'PNG_pixels':list(image.size),'PNG_DPI':list(image.info['dpi']),
                'page_inches':[page.rect.width/72,page.rect.height/72]})
    write(out/'publication_QA_v7.json',json.dumps({'all_sources_unchanged':True,'all_text_within_canvas':True,
        'all_text_bbox_collision_checks_pass':True,'review_pages':len(review),'figures':qa,
        'trace_records_verified':True,'paper_exports_contain_full_caption':False,
        'packager_sha256':sha(Path(__file__))},indent=2))
    write(out/'README_zh.md','''# ContractKV 主图 V7（2026-10-17）

本版借鉴新修改意见，重新安排 Fig. 2–6 的信息层级；Fig. 1 与正文未改，V6完整保留。

[五图审阅PDF（含独立图注）](ContractKV_Fig2-6_review_v7.pdf) · [总览](all_figures_preview_v7.png) · [图注草稿](captions_v7.md) · [完整配套表](supporting_tables_v7.md)

## 主要变化

- **Fig. 2**：吞吐、业务+认证prefill、Mean Readiness TTFT。加入净工作量下降45.4/14.6/10.9%和平均readiness下降43.9/12.1/4.0%。认证工作数字直接标出。按作者偏好去掉柱顶重复圆点，三次重复数值及范围保存在配套表中。
- **Fig. 3**：模型×HotpotQA/RepoBench覆盖矩阵；继承L0用灰色斜线单独标明。右侧压缩零分歧统计，并保留raw正分子集。下方是真实日志链：7 IDs→PASS→COMMITTED 888块→t3相同7 IDs，附原始记录和哈希。
- **Fig. 4**：25倍调用摊销、7.7倍未隐藏成本摊销成为左侧主视觉；失败候选零提升居中；右侧展示D2保留D1约97.0%的实测均值goodput。零提升仅针对被拒候选，不能解释为raw fallback完全不缓存。
- **Fig. 5**：在80%负载处同时标0.173→0.831和+0.658 req/s，4.81倍限定为该点。右侧突出+381 free blocks，并加入同批80-identity密度单元的1.152→11.033 req/s。右侧是分层SLO wave replay，左侧是500-ms开放到达，不能合并口径或据此把全部吞吐改善归因为headroom。
- **Fig. 6**：保留真实负值，淡色标识50–75%观测跃升区间；右侧改为reuse distance/hot-set skew，并提示round-robin收益接近零。纵轴仍是TTFT reduction。

## 术语、版式和证据取舍

Raw/reference灰色、ContractKV深蓝、qualified reuse青绿、认证成本橙色、拒绝仅少量红色、D1中性蓝灰。每张单图仅包含紧凑图形、必要协议标记和图例，不内嵌长caption；含标题和图注的合订PDF仅用于审阅。PDF/SVG用于LaTeX，PNG为600 dpi预览。

Earlier audit的2,442/2,442 raw正分已逐请求复核，并按任务家族/协议导出`earlier_score_credit_audit_v7.csv`。RULER字符串匹配、QA F1和代码相似度不是统一准确率，因此主图不再把该聚合正分数当作正确回答证据。p99、全路由变化、独立Qwen来源与历史slack、跨栈质量表均保留在配套表。

真实轨迹选择规则是文件顺序中的首个获准证书及其首个同作用域未来请求，不按结果好坏挑选。`trace_log_excerpt_v7.json`保存六条完整选中记录、原文件SHA256和行号；其commit证据来自实际COMMITTED响应与随后native命中，不伪称存在单独的BlockStored事件。完整原日志仍在原实验归档。

## 复现

```powershell
python submission/build_tsc_revision_figure_data_v7.py
python submission/gen_tsc_figures_v7.py
python submission/package_tsc_revision_figures_v7.py
```

`plot_sources_v7.zip`包含所需统计表、V6数据构建依赖、四份V7源码以及实际轨迹选中记录。在独立目录解包后可重画；若要独立重新选择轨迹，请恢复原primary raw/metrics归档后执行`extract_tsc_revision_trace_v7.py`。字体及依赖版本、SHA256、越界/文字碰撞、矢量与字体检查保存在各manifest和QA JSON中。未运行新GPU实验。
''')
    print(json.dumps({'figures':len(qa),'bundle_members':len(source_paths),'review_pages':len(review),
                      'vector_and_actual_text_QA':'PASS'}))


if __name__=='__main__':main()
