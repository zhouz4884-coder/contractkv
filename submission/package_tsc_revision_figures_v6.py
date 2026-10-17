"""Captions, separate-protocol tables, vector PDF review and figure QA."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import fitz
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
FIGURES=[
 ('fig2_strict_serving_performance','Fig. 2. Strict Serving Performance'),
 ('fig3_observed_generation_behavior','Fig. 3. Certification Preserves Observed Free-Running Behavior'),
 ('fig4_certification_and_template_value','Fig. 4. Certification, PSTP and Service-Template Amortization'),
 ('fig5_service_scale_and_physical_reuse','Fig. 5. Service Scale and Physical KV Reuse'),
 ('fig6_operating_region','Fig. 6. Operating Region')]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def table(headers,values):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(map(str,row))+' |' for row in values])


def write(p,text):p.write_bytes((text.rstrip()+'\n').encode('utf-8'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'Paper/figures/revision_20261017');a=p.parse_args();out=a.output
    d=json.loads((out/'figure_data_v6.json').read_text());render=json.loads((out/'render_manifest_v6.json').read_text())
    assert render['all_text_inside_canvas']
    captions=[
      ('Three models are evaluated on the same six held-out HotpotQA/RepoBench sources with faithful 16K inputs, '
       'query-scoped raw-witness qualification, greedy decoding and zero tool slack. '
       '(a) Throughput is normalized to each model\'s raw service path; the service wall includes initial business answers, '
       'planning, successful and failed certification, waiting, scoring and logging. Model startup and common preflight precede this interval. '
       'Whiskers show the minimum and maximum of three paired process repetitions. '
       '(b) New prefill counts are per 600-business-request run; orange segments add certification, including witness tokens. '
       'Counts are initial scheduler prompt-minus-hit observations. '
       '(c) Coverage uses 1,620 future requests per model, giving 42.22%, 21.11% and 16.67%.'),
      ('(a) Future routes in the faithful validation retain every raw/L0 request. Compiled requests are further divided by '
       'whether the paired raw reference receives a positive frozen task score. Qwen, Mistral and Llama have '
       '684/684, 258/342 and 90/270 positive-score compiled pairs. '
       '(b) The earlier bounded-input audit (50 sources; single-session and template-fanout protocols) observed '
       '0/2,442 compiled future output-ID differences. The faithful held-out validation (six sources; template fanout) observed '
       '0/1,296. These are finite, scoped empirical observations. Positive scorer credit alone does not establish answer correctness. '
       'Tenant and process repetitions remain correlated; full-route score changes are retained in the supporting tables.'),
      ('(a) The five-process same-engine control reports 500-ms SLO goodput of 1.472 req/s for D1\'s frozen safe layout '
       'and 1.428 req/s for full D2, including registration; whiskers are repeat min-max. D2 makes four verifier calls per trace. '
       '(b) Two separate live Qwen configurations each reject 10/10 harmful, dependency-valid layouts and publish zero rejected tokens. '
       '(c) The deployment certificate-granularity ablation holds the safe layout fixed across session/template modes. '
       'Across three repetitions of 1,125 future requests, calls per trace fall from 125 to 5 and unhidden cost falls from '
       '25.05 to 3.24 ms per future request. The two measures use independent axes. Panel populations and protocols remain separate.'),
      ('(a) The original deployment-template protocol measures absolute 500-ms SLO goodput under frozen open-arrival loads '
       '(Qwen3-8B; 25 authorized tenants per template; three fresh processes per condition). The 4.81x annotation is the '
       '80%-load point. (b) The distinct 80-identity density condition reduces peak allocator-used blocks from 530 to 149 '
       '(71.9%) in a 2,386-block pool; minimum free blocks rise from 1,856 to 2,237. Registered tenant identities describe '
       'the authorized workload population, rather than simultaneously executing GPU requests. Block counts measure allocator '
       'occupancy. These original deployment protocols are separate from the strict closed-loop faithful-input study.'),
      ('(a) The 40-identity deployment sweep measures mean TTFT change against its paired native baseline as authorized sharing '
       'increases. Every point is derived from the saved CSV, including -3.2% at zero sharing. '
       '(b) A separate frozen working-set sweep compares round-robin and Zipf arrivals over 5, 25 and 50 active templates, '
       'showing net mean TTFT reduction. The plotted metric is latency reduction, with prefix-hit ratios retained in the data table. '
       'Together the panels delimit the measured reuse-density and residency region; qualification remains distinct from physical KV residency. '
       'Frozen-gate results are provided in a supporting table.')]
    caption_md=['# ContractKV revision figure captions','',
                'Draft captions for the new figure files. Manuscript source and Fig. 1 are unchanged.','']
    for (stem,title),caption in zip(FIGURES,captions):
        caption_md.extend(['## '+title,'',caption,'',f'[PDF]({stem}.pdf) · [SVG]({stem}.svg) · [PNG]({stem}.png)',''])
    write(out/'captions_v6.md','\n'.join(caption_md))
    lines=['# Supporting tables: keep operating protocols separate','',
           'Generated from the same source manifest as the figures. No new GPU measurements were run.','',
           '## A. Additional Qwen six-source validation (separate source set)','',
           'These six sources differ from the six-source three-model main validation. The cost variant was rejected as the default.','']
    lines.append(table(['Policy','Full wall / raw','Compiled future pairs','Coverage'],[
        ['Strict raw-witness, original cost gate' if x['policy']=='risk-tail' else 'Cost-adapted candidate (not selected)',
         f"{float(x['full_wall_goodput_multiplier']):.3f}x",f"{x['compiled_future_pairs']:,} / {int(x['pairs']):,}",
         f"{100*x['compiled_future_pairs']/int(x['pairs']):.2f}%"] for x in d['additional_Qwen_validation']]))
    lines+=['','## B. Original deployment latency with tool-slack accounting','',
            'Net mean TTFT charges verification exposure beyond the frozen tool-slack window. These rows retain the original input and deployment protocols.','',
            table(['Model/configuration','Tool slack','Net mean TTFT reduction','Fresh-process pairs'],[
                [x['model'],f"{x['tool_slack_ms']:,} ms",f"{x['net_TTFT_reduction_pct']:.2f}%",x['repeats']] for x in d['legacy_slack_TTFT']]),
            '', '## C. Matched-native quality distributions (no cross-stack speed ranking)','',
            table(['Method','Own matched baseline','Pairs','Baseline mean','Method mean','Score up >0.03','Score down >0.03','No material change'],[
              [{'cacheblend':'CacheBlend (adapted LMCache path)','contractkv':'ContractKV (vLLM)',
                'manual_oracle':'Manual layout oracle (offline)','sglang_certified':'SGLang frozen certified layout'}[x['method']],
               {'cacheblend_raw':'LMCache separator-matched raw','vllm_apc':'vLLM APC raw','sglang_raw':'SGLang raw RadixAttention'}[x['matched_baseline']],x['paired_requests'],f"{float(x['baseline_mean_score']):.6f}",
               f"{float(x['candidate_mean_score']):.6f}",x['material_improvements'],x['material_regressions'],
               int(x['paired_requests'])-int(x['material_improvements'])-int(x['material_regressions'])]
              for x in d['matched_quality_tables']]),
            '', '## D. Frozen prospective gate (moved from Fig. 6)','',
            table(['Stable tokens','Reuse count','Tool slack (ms)','Gate accepted','Actual route','Observed net benefit (ms)'],[
                [x['stable_prefix_tokens'],x['future_reuses'],x['tool_slack_ms'],x['gate_accepted'],x['effective_policy'],
                 f"{float(x['observed_net_benefit_ms']):.2f}"] for x in d['frozen_gate_table']]),
            '', 'Rejected lanes report the actual raw-fallback route. The two accepted lanes are not evidence that every workload is profitable.','',
            '## E. Density goodput retained from the original Fig. 5','',
            'The density study uses class-specific TTFT thresholds (750/1,500/3,000 ms). Its ALL goodput is a separate metric from the 500-ms curve in Fig. 5(a).','',
            table(['Registered identities','Policy','Class-specific SLO goodput (req/s)','Peak used blocks','Minimum free blocks'],[
                [x['tenants'],x['policy'],f"{x['tiered_SLO_goodput']:.3f}",f"{x['peak_used_blocks']:.1f}",f"{x['minimum_free_blocks']:.1f}"] for x in d['density']]),
            '', '## F. Primary strict-validation tail and full-route results','',
            table(['Model','Raw readiness p99 (ms)','CKV readiness p99 (ms)','p99 reduction 95% source/repeat CI (%)','Future material drops (all routes)'],[
                [x['label'],f"{x['raw_ready_p99_ms']:.1f}",f"{x['CKV_ready_p99_ms']:.1f}",
                 f"[{x['p99_reduction_CI95_low']:.3f}, {x['p99_reduction_CI95_high']:.3f}]",x['all_future_material_drops']] for x in d['strict']]),
            '', 'Full wall throughput gains coexist with these tail costs. The future-only table excludes the additional Mistral initial-business material drop recorded in the full experimental report.','',
            table(['Audit','Audited / compiled sources','Compiled future pairs','Compiled output-ID differences','Raw-positive compiled pairs','All-route future material drops'],[
                [x['label'],f"{x['distinct_sources']} / {x['distinct_compiled_sources']}",x['compiled_future_pairs'],x['ID_divergences'],x['raw_positive_pairs'],x['all_route_material_drops']] for x in d['behavior_audits']]),
            '', '## G. Primary new-prefill accounting (counts per process)','',
            table(['Model','Raw business','CKV business','Certification incl. witness','CKV total','Count reduction'],[
                [x['label'],f"{x['raw_business_prefill_per_repeat']:,}",f"{x['CKV_business_prefill_per_repeat']:,}",
                 f"{x['qualification_prefill_per_repeat']:,}",f"{x['CKV_business_prefill_per_repeat']+x['qualification_prefill_per_repeat']:,}",
                 f"{100*(1-(x['CKV_business_prefill_per_repeat']+x['qualification_prefill_per_repeat'])/x['raw_business_prefill_per_repeat']):.2f}%"] for x in d['strict']]),
            '', 'Counts are initial scheduler observations, rather than an integral of GPU kernels or a VRAM estimate.']
    write(out/'supporting_tables_v6.md','\n'.join(lines))
    mappings={old:new+'.pdf' for old,(new,_) in zip(['fig2_global_benefit.pdf','fig3_llama_baselines.pdf',
               'fig4_verification_economics.pdf','fig5_service_locality.pdf','fig6_operating_region.pdf'],FIGURES)}
    write(out/'manuscript_figure_map_v6.json',json.dumps({'old_to_new':mappings,'manuscript_edited':False,'Fig1':'user maintained'},indent=2))
    review=fitz.open();font=render['resolved_font'];font_name='ReviewArial'
    for (stem,title),caption in zip(FIGURES,captions):
        page=review.new_page(width=612,height=430)
        page.insert_font(fontname=font_name,fontfile=font)
        titlebox=fitz.Rect(24,14,588,46)
        result=page.insert_textbox(titlebox,title,fontname=font_name,fontsize=12,color=(.08,.20,.32))
        assert result>=0
        with fitz.open(out/(stem+'.pdf')) as src:
            page.show_pdf_page(fitz.Rect(24,52,588,305),src,0,keep_proportion=True)
        result=page.insert_textbox(fitz.Rect(24,317,588,419),caption,fontname=font_name,fontsize=8.1,
                                   lineheight=1.25,color=(.12,.14,.16))
        assert result>=0,(stem,result)
    review.set_metadata({'title':'ContractKV revised figures 2–6','author':'ContractKV','subject':'Figure review, no manuscript changes'})
    review.save(out/'ContractKV_Fig2-6_review.pdf',garbage=4,deflate=True)
    thumbs=[]
    for (stem,title) in FIGURES:
        im=Image.open(out/(stem+'.png')).convert('RGB');im.thumbnail((1050,480))
        card=Image.new('RGB',(1110,555),'white');draw=ImageDraw.Draw(card)
        face=ImageFont.truetype(font,22)
        draw.text((22,14),title.split('. ',1)[0]+'. '+title.split('. ',1)[1][:66],font=face,fill='#15599A')
        card.paste(im,((1110-im.width)//2,58+(480-im.height)//2));thumbs.append(card)
    sheet=Image.new('RGB',(2220,1665),'#E9EEF2')
    for i,im in enumerate(thumbs):sheet.paste(im,((i%2)*1110,(i//2)*555))
    ImageDraw.Draw(sheet).text((1135,1150),'Editable PDF + SVG\n600 dpi PNG\nMeasured data + code',font=ImageFont.truetype(font,30),fill='#15599A',spacing=15)
    sheet.save(out/'all_figures_preview.png')
    qa=[]
    key_text=[['1.619','1.109','1.070','42.22%','21.11%','16.67%'],
              ['0 / 2,442','0 / 1,296','1,032 / 1,296'],
              ['1.472','1.428','125','25.05','3.24','10 / 10'],
              ['530','149','71.9%','2,386','4.81'],['-3.2%','93.3%','84.6%','73.4%']]
    for (stem,_),expected in zip(FIGURES,key_text):
        with fitz.open(out/(stem+'.pdf')) as doc:
            assert len(doc)==1 and abs(doc[0].rect.width-7.16*72)<.01
            fonts=doc.get_page_fonts(0,full=True)
            assert all(x[2]!='Type3' for x in fonts)
            embedded=all(bool(doc.extract_font(x[0])[3]) for x in fonts)
            assert embedded
            assert not doc[0].get_images()
            text=' '.join(doc[0].get_text().split())
            assert all(s in text for s in expected),(stem,expected,text)
            png=Image.open(out/(stem+'.png'));assert png.width==4296
            root=ET.parse(out/(stem+'.svg')).getroot()
            nodes=[x.tag.rsplit('}',1)[-1] for x in root.iter()]
            assert nodes.count('image')==0 and nodes.count('text')>0
            qa.append({'figure':stem,'PDF_page_inches':[doc[0].rect.width/72,doc[0].rect.height/72],
                'PDF_fonts_embedded':embedded,'Type3_fonts':0,'SVG_editable_text_nodes':nodes.count('text'),
                'SVG_raster_image_nodes':0,'PDF_raster_image_nodes':0,
                'key_values_present_in_actual_PDF_text':expected,
                'PNG_pixels':list(png.size),'PNG_DPI':list(png.info.get('dpi',()))})
    source_manifest=json.loads((out/'source_manifest_v6.json').read_text())
    assert all(sha(ROOT/x['path'])==x['sha256'] for x in source_manifest['sources'])
    bundle_paths=[ROOT/x['path'] for x in source_manifest['sources']]+[
        ROOT/'submission/build_tsc_revision_figure_data_v6.py',ROOT/'submission/gen_tsc_figures_v6.py',Path(__file__)]
    bundle_paths=list(dict.fromkeys(bundle_paths))
    with zipfile.ZipFile(out/'plot_sources_v6.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in bundle_paths:z.write(f,f.relative_to(ROOT).as_posix())
    bundle={'archive':'plot_sources_v6.zip','sha256':sha(out/'plot_sources_v6.zip'),
            'files':[{'path':f.relative_to(ROOT).as_posix(),'sha256':sha(f),'bytes':f.stat().st_size} for f in bundle_paths]}
    write(out/'plot_sources_manifest_v6.json',json.dumps(bundle,indent=2))
    write(out/'publication_QA_v6.json',json.dumps({'all_source_SHA256_unchanged':True,
         'all_text_within_canvas':render['all_text_inside_canvas'],'figures':qa,
         'review_PDF_pages':len(review),'manual_visual_review':'Figures 2–6 inspected; shortened overflow titles, moved legends outside data, separated certificate units.',
         'packager_sha256':sha(Path(__file__))},indent=2))
    notes='''# ContractKV 主图重绘（2026-10-17）

已完成 Fig. 2–6，Fig. 1 留给作者。所有旧图和正文保留，新文件集中于本目录。

[五页矢量审阅 PDF](ContractKV_Fig2-6_review.pdf) · [五图总览](all_figures_preview.png) · [英文图注草稿](captions_v6.md) · [配套表格](supporting_tables_v6.md)

## 故事主线与设计决定

| 图 | 要回答的问题 | 绘制方式 |
|---|---|---|
| Fig. 2 | 严格作用域、真实任务、零 slack 下能否有全成本收益？ | 双栏宽三面板；1.619/1.109/1.070×；prefill 加入认证；未来覆盖分母 1,620/model |
| Fig. 3 | 收益对应哪些获准请求，真实输出是否变化？ | 路由堆叠再区分 raw 正分/零分；并列 0/2,442 和 0/1,296，保留来源数 |
| Fig. 4 | 治理开销如何进入服务，模板共享为什么值得？ | D1/D2 真值及重复范围；两组 live 坏布局拒绝；次数和毫秒分别画 |
| Fig. 5 | 原部署协议能否产生实际服务与物理复用收益？ | 绝对 SLO goodput；530→149 allocator-used blocks；4.81×仅小标单点 |
| Fig. 6 | 什么复用密度和驻留条件支持收益？ | 授权共享曲线与工作集曲线；gate 移入配套表 |

保持原 v5 的蓝/青/灰语义配色，复用其 set_style，增加明确的浅蓝斜线编码。先以原绘图方法生成，再按 scientific-figure-making 的图例和边界规则修正首版拥挤；未使用生成式位图代替实验曲线。

## 与最初建议相比的调整

- Fig. 3 不只重复 Fig. 2 覆盖率：额外分出 684/684、258/342、90/270 的 raw 正分子集，行为一致与参考质量同时可见。
- Fig. 5 将身份数 goodput 的完整旧曲线留在配套表，主图聚焦开放到达的绝对 goodput 和实际物理 block 数。两者属于原部署协议，主图与 Fig. 2 的新保真闭环协议明确分开。
- Fig. 6 直接从配对 CSV 计算共享收益：0% 共享为 −3.20%，旧生成器写成 0；75/100% 由原粗略 93.4% 改为源 CSV 的 93.3%。没有改实验记录或截去负值。
- 旧 TTFT 对照的工具 slack 分别为 Qwen/Mistral/14B 的 2,000 ms、Llama 的 6,000 ms；均移入配套表。另六来源 Qwen 1.803×单列，没有混入三模型柱图。
- 4.81×使用其绝对曲线的均值单点，不沿用来源链未闭合的旧区间。新 Fig. 2/4 的 whisker 是进程重复 min–max，图注明确该定义。
- 全路由变化、p99 代价、未选成本变体和 CacheBlend 各自 native baseline 的质量分布都保留在配套表。

## 文件与复现

- 每图 PDF / SVG / 600-dpi PNG，统一双栏宽 7.16 英寸。PDF 字体嵌入；SVG 文字可编辑。
- `figure_data_v6.json`：所有绘图值与协议边界。
- `source_manifest_v6.json`：23 个原始数据/风格依据的路径和 SHA256。
- `plot_sources_v6.zip`：所用原始统计表、v5 配色代码及三份新脚本的完整快照，便于在独立目录复现。
- `render_manifest_v6.json` / `publication_QA_v6.json`：字体、尺寸、向量文本与越界检查。
- `manuscript_figure_map_v6.json`：旧图文件名与新图的映射，尚未修改 LaTeX 引用。

从仓库根目录运行：

```powershell
python submission/build_tsc_revision_figure_data_v6.py
python submission/gen_tsc_figures_v6.py
python submission/package_tsc_revision_figures_v6.py
```

生成依赖：Matplotlib、NumPy、Pillow、PyMuPDF。绘图沿用本机 Arial，实际字体身份记录于 manifest。全程未启动 GPU 实验。
'''
    write(out/'README_zh.md',notes)
    print(json.dumps({'figures':len(qa),'all_fonts_embedded':True,'SVG_text_editable':True,'review_pages':len(review)}))


if __name__=='__main__':main()
