"""Generate claim-bounded Markdown only after full independent recomputation."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase12_prefix_cache_ab import percentile
STUDY=Path('results/tsc_behavior_scope_repair_20261020')
POLICIES=['Raw-authorized','Deployment','Strict-exact']
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(str(v) for v in r)+' |' for r in rows])
def main(workspace,evidence,output):
    study=workspace/STUDY;proof=read(study/'all_local_independent_recompute_v1.json');assert proof['status']=='PASS'
    assert Path(proof['restore_root']).resolve()==evidence.resolve()
    oldscope=read(study/'prior_scope_audit_v1.json');prefix=read(study/'prior_actual_prefix_audit_v1.json')
    dev=read(study/'development_analysis_v5.json');val=read(study/'validation_analysis_v5.json')
    assert dev['status']==val['status']=='PASS';data=evidence/STUDY
    states={phase:read(data/(phase+'_execution_state_v4.json')) for phase in ['development','validation']}
    assert all(r['status']=='COMPLETE_PENDING_INDEPENDENT_ANALYSIS' for r in states.values())
    rows=[];quality=[];sources=[];floor_count=0;ref_kind=Counter();endings=Counter();raw_positive=Counter();per_repeat=[]
    allbusiness={};registrations=[]
    for phase,analysis in [('development',dev),('validation',val)]:
        plan=read(data/(phase+'_jobs_v4.json'))
        for job in plan['jobs']:
            path=data/'runs'/job['id']/'attempt1/responses.jsonl'
            rr=lines(path);bs=[r for r in rr if r['row_type']=='business'];allbusiness[phase,job['id']]=bs
            endings.update((phase,r['level'],r['result']['finish_reason']) for r in bs)
            for reg in [r for r in rr if r['row_type']=='registration']:
                registrations.append((phase,job,reg));c=reg['certificate']
                if c['certificate_issued']:
                    assert c['minimum_margin_guard_passed'] and c['raw_margin_min']>=.0625 and c['candidate_margin_min']>=.125 and c['terminal_stop_margin']>=.125
                    assert c['committed_tokens']>0 and c['committed_tokens']%16==0;floor_count+=1
                if job['policy']=='Strict-exact':ref_kind[reg['reference_kind']]+=1
        for model in plan['models']:
            cs=[c for c in analysis['cells'] if c['job']['model']==model]
            raw=sum(c['wall_s'] for c in cs if c['job']['policy']=='Raw-authorized')
            for policy in POLICIES:
                ss=[c for c in cs if c['job']['policy']==policy];wall=sum(c['wall_s'] for c in ss);n=sum(c['offered'] for c in ss)
                comp=sum(c['compiled_business'] for c in ss);ctrl=sum(c['full_controller_ms'] for c in ss)/1000
                prefill=sum(sum(c['native_new_prefill_by_kind'].values()) for c in ss)
                requests=[r for c in ss for r in allbusiness[phase,c['job']['id']]]
                readiness=[r['ready_ttft_ms'] for r in requests]
                future=sum(r['access']>0 for r in requests)
                rows.append(dict(phase=phase,model=model,policy=policy,requests=n,compiled=comp,future=future,
                    future_compiled=sum(r['compiled'] and r['access']>0 for r in requests),wall_s=wall,
                    full_wall_throughput_ratio=raw/wall,controller_s=ctrl,RPCs=sum(c['actual_verification_RPCs'] for c in ss),
                    actual_all_cost_new_prefill=prefill,ready_TTFT_mean_ms=statistics.mean(readiness),
                    ready_TTFT_p95_ms=percentile(readiness,.95),ready_TTFT_p99_ms=percentile(readiness,.99)))
                if policy!='Raw-authorized':
                    pp=[p for p in analysis['pairs'] if p['model']==model and p['policy']==policy];cp=[p for p in pp if p['compiled']]
                    quality.append(dict(phase=phase,model=model,policy=policy,pairs=len(pp),compiled_pairs=len(cp),
                        compiled_ID_EOS_changes=sum(not p['IDs_and_EOS_equal'] for p in cp),compiled_drops=sum(p['down'] for p in cp),
                        allroute_ID_EOS_changes=sum(not p['IDs_and_EOS_equal'] for p in pp),allroute_down=sum(p['down'] for p in pp),
                        allroute_up=sum(p['up'] for p in pp),compiled_Raw_positive_score=sum(p['Raw_score']>0 for p in cp)))
                if phase=='validation':
                    for repeat in sorted({c['job']['repeat'] for c in ss}):
                        c=next(c for c in ss if c['job']['repeat']==repeat);base=next(c0 for c0 in cs if c0['job']['policy']=='Raw-authorized' and c0['job']['repeat']==repeat)
                        per_repeat.append(dict(model=model,policy=policy,repeat=repeat,wall_s=c['wall_s'],Raw_ratio=base['wall_s']/c['wall_s']))
            for source in sorted({p['source'] for p in analysis['pairs'] if p['model']==model}):
                for policy in ['Deployment','Strict-exact']:
                    pp=[p for p in analysis['pairs'] if p['model']==model and p['source']==source and p['policy']==policy]
                    sources.append(dict(phase=phase,model=model,source=source,policy=policy,requests=len(pp),compiled=sum(p['compiled'] for p in pp),
                        Raw_mean=statistics.mean(p['Raw_score'] for p in pp),policy_mean=statistics.mean(p['score'] for p in pp),
                        down=sum(p['down'] for p in pp),up=sum(p['up'] for p in pp),ID_changes=sum(not p['IDs_and_EOS_equal'] for p in pp)))
    registration_costs=[]
    for phase,job,reg in registrations:
        cert=reg['certificate'];attempts=cert['attempts']
        registration_costs.append(dict(phase=phase,model=job['model'],repeat=job['repeat'],policy=job['policy'],source=reg['source_group'],
            tenant=reg['tenant'],turn=reg['turn'],PASS=cert['certificate_issued'],reason=cert.get('failure_reason',''),
            complete_controller_ms=reg['full_controller_ms'],verification_HTTP_ms=sum(a['verification_ms'] for a in attempts),
            failed_HTTP_ms=sum(a['verification_ms'] for a in attempts if not a.get('certificate_issued')),
            actual_certified_prefix_read_tokens=sum(a.get('cached_prefix_read_tokens',0) for a in attempts),
            committed_tokens=cert.get('committed_tokens',0)))
    summary=dict(status='PASS',aggregate=rows,quality=quality,source_quality=sources,validation_per_repeat=per_repeat,registration_costs=registration_costs,
        floor_and_commit_qualified_certificates_checked=floor_count,strict_reference_kinds=dict(ref_kind),
        terminations=[dict(phase=k[0],level=k[1],finish=k[2],count=v) for k,v in endings.items()],
        independent_recompute_receipt_sha256=sha(study/'all_local_independent_recompute_v1.json'),source_sha256=sha(Path(__file__)))
    details=study/'final_descriptive_tables_v1.json'
    with details.open('x',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2);f.write('\n')
    p=[];add=p.append
    add('# ContractKV：精确行为作用域修复与独立验证总报告\n')
    add('本轮先修代码，再做预注册对照；不修改论文或 Response Letter。旧 27 单元、36 次 compiled 掉分和全部输出差异保留。本文数值仅来自本轮实际执行和独立复算；不会把旧 Deployment 的高 Goodput 认领为新严格入口的结果。\n')
    add('## 1. 需要修复的边界，以及没有失效的机制\n')
    add('旧 Session 每组 72 个对象/RPC（24×3 重复）仅对应 3 条 canonical prompt，绝不是 72 条独立 prompt。对六个真实来源枚举 8 tenant×9 turn，稳定文本各只有 1 种，完整 L3 输入各有 72 种；旧 3,456 次 compiled 的实际稳定 Token 前缀全部匹配证书。模板物理复用和资格摊销证据成立。\n')
    add('需要补齐的是另外两个判断：部署 compiled 见证不能充当具体请求的 Raw 等价见证；旧 admit 的保存 plan 自比不能替代对实际派发前缀的带内校验。前缀字节相同并不能推出重排前后的整个生成行为相同。旧 doc107 的 36 个下降来自 6 个条件，在两策略×三重复中复现；保留官方 >0.03 下降判定。\n')
    add('## 2. 实际代码修复\n')
    add('- `contractkv_exact_behavior.py`：控制器内部区分 `RAW_QUERY` 与 `COMPILED_DEPLOYMENT`，将完整 Raw/Candidate Prompt IDs、模型/运行时/生成设置、授权域/epoch、Raw 输出和 EOS、实际证书/提交边界绑定为精确行为记录。\n- `tsc_behavior_scope_protocol_v2.py`：同时要求原有模板授权绑定和精确 Raw 行为记录；对实际 tokenizer Candidate IDs 按证书边界重新计算原有稳定前缀哈希。没有证据、后缀变更、签名/epoch/授权不符均不得进入 compiled。\n- `tsc_behavior_scope_client_v3.py`：首次业务是实际授权 Raw 请求并记录见证；候选只在私有 namespace 自由生成。Raw/候选 IDs 与 EOS 一致后，复用既有单次 Token/EOS verifier 和 PSTP；失败保留 Raw，只有 PASS 发布共享候选前缀。\n- 唯一输入不投入候选生成/认证；实际重复输入才复用精确资格。所有 Raw、fallback、private reference、verifier、compiled 仍走统一授权缓存入口。CALC、PSTP、Raw 0.0625 / Candidate/EOS 0.125 floor、任务评分均未放宽。\n')
    add('模板身份与物理前缀可保持共享；完整行为资格随精确输入数 U 增长。此修复没有证明任意动态后缀均可由一次模板 Raw 认证覆盖，也没有新建第五项算法贡献。\n')
    add('## 3. 冻结协议和统计单位\n')
    add('开发：两个新 HotpotQA（doc40/doc35）和一个新 RepoBench；独立：doc80/doc122/doc61 和 SkunkworksAI/BakLLaVA。从既有池按冻结 seed:source 哈希及容量选取，排除所有旧/预留来源；gold 不参与选样、裁剪或在线准入。独立四来源均保留原始文本，common16K、完整问题和代码格式；预算 QA128、Repo384，temperature0/seed14014。\n')
    add('每来源两条模型可见精确条件 `(tenant00,turn1)`、`(tenant01,turn1)`；开发各访问4次，独立各8次。调用序号不进入 Prompt，原 tenant/turn TOOL_OBS 不删除、不合并。授权表支持8个身份，本轮实际活跃2个，不声称8路GPU并发。按访问轮次→固定来源→两条件轮转；三臂 Raw/Deployment/Strict-exact 使用同一内容、顺序、授权共享关系和同模型同物理GPU。\n')
    add('独立三臂×两模型×两 fresh-process 重复=12 cells、768业务；加开发共18 cells、912业务。Repo继承两模型已有L0，没有借本轮解禁；Llama不在本轮新协议范围。冷在线时钟在准备前开始，含首次Raw见证、私有候选、成功/失败认证、绑定、客户端等待及最终排空；模型加载另记，不含在服务 wall 中。零slack，但本轮是闭环积压与固定轮转，不是开放到达SLO容量实验。\n')
    add('## 4. 开发结果（不能代替独立结果）\n')
    add(table(['模型','路径','业务/compiled','完整wall(s)','相对Raw吞吐','认证RPC','Controller(s)'],[
        [r['model'],r['policy'],f"{r['requests']}/{r['compiled']}",f"{r['wall_s']:.3f}",f"{r['full_wall_throughput_ratio']:.3f}×",r['RPCs'],f"{r['controller_s']:.3f}"] for r in rows if r['phase']=='development'])+'\n')
    add('两模型各12严格compiled配对，ID/EOS差异与掉分均为0，且这24个Raw参考分数全部>0。四次访问时Qwen略未回本，不能写成全线收益；Mistral已回本。是否进入独立阶段只按事前固定八次访问成本屏幕与行为/物理门槛判断。开发原包217成员、本地复算所有值完全一致。\n')
    add('## 5. 独立完整成本结果\n')
    add(table(['模型','路径','业务/compiled','完整wall(s)','相对Raw吞吐','RPC','Controller(s)','含认证新Prefill'],[
        [r['model'],r['policy'],f"{r['requests']}/{r['compiled']}",f"{r['wall_s']:.3f}",f"{r['full_wall_throughput_ratio']:.3f}×",r['RPCs'],f"{r['controller_s']:.3f}",r['actual_all_cost_new_prefill']] for r in rows if r['phase']=='validation'])+'\n')
    add('上表吞吐比=相同业务量的Raw完整wall÷对应完整wall；包含全部失败费用。Controller仅指每次注册完整工作，首次Raw已计业务；不能把其差额当纯GPU验证成本。Prefill是引擎实际初始新增Token计数，含私有参考和验证，不换算为GPU时间。\n')
    add(table(['严格模型','compiled/全部业务','compiled/后续访问（access>0）'],[
        [r['model'],f"{r['compiled']}/{r['requests']} ({100*r['compiled']/r['requests']:.2f}%)",f"{r['future_compiled']}/{r['future']} ({100*r['future_compiled']/r['future']:.2f}%)"]
        for r in rows if r['phase']=='validation' and r['policy']=='Strict-exact'])+'\n')
    add(table(['模型','路径','重复1吞吐比','重复2吞吐比'],[
        [model,policy]+[f"{next(r['Raw_ratio'] for r in per_repeat if r['model']==model and r['policy']==policy and r['repeat']==rep):.3f}×" for rep in [1,2]]
        for model in val['models'] for policy in ['Deployment','Strict-exact']])+'\n')
    add(table(['模型','路径','Mean/P95/P99 readiness TTFT(ms)'],[
        [r['model'],r['policy'],f"{r['ready_TTFT_mean_ms']:.1f} / {r['ready_TTFT_p95_ms']:.1f} / {r['ready_TTFT_p99_ms']:.1f}"] for r in rows if r['phase']=='validation'])+'\n')
    add('Readiness从前一个业务完成到本请求首Token计时，包含期间同步资格等待；首请求从服务epoch计时。两次进程重复与四个来源不足以支持普遍显著性、生产容量或通用p99保证；逐重复与来源表全部给出。\n')
    add('## 6. 行为保持与绝对任务效用\n')
    add(table(['模型','路径','compiled配对','compiled ID/EOS变/降分','全路由ID/EOS变/降分/升分','compiled中Raw分数>0'],[
        [q['model'],q['policy'],q['compiled_pairs'],f"{q['compiled_ID_EOS_changes']} / {q['compiled_drops']}",f"{q['allroute_ID_EOS_changes']} / {q['allroute_down']} / {q['allroute_up']}",q['compiled_Raw_positive_score']]
        for q in quality if q['phase']=='validation'])+'\n')
    add('分数变化按固定>0.03升/降分，两者之间为无实质变化；输出差异即使升分也不算严格行为认证成功。Raw等价亦不意味着答案正确。以下为每个独立来源的官方任务分数，不把均分提高用于删除单请求下降：\n')
    add(table(['模型','来源','路径','compiled/业务','Raw均分','路径均分','下降/上升/ID变化'],[
        [s['model'],s['source'],s['policy'],f"{s['compiled']}/{s['requests']}",f"{s['Raw_mean']:.5f}",f"{s['policy_mean']:.5f}",f"{s['down']}/{s['up']}/{s['ID_changes']}"] for s in sources if s['phase']=='validation'])+'\n')
    add('## 7. 资格、物理状态与故障保留\n')
    add('开发实际物理命中：'+json.dumps(dev['physical_hits'],ensure_ascii=False)+'；独立：'+json.dumps(val['physical_hits'],ensure_ascii=False)+'。资格不是完整驻留证明；零/部分命中仍全部计费。所有合格证书的点状margin/EOS与16-token提交边界均独立核验，共'+str(floor_count)+'条PASS记录。\n')
    add('逐作用域的完整Controller、验证HTTP、失败HTTP、实际已认证前缀读取量和提交量都在 `final_descriptive_tables_v1.json` 的 registration_costs 保留；成功证书也可能因驻留损失而重新计算。现有PSTP前缀辅助验证允许后续独立行为资格读取已认证稳定前缀，但仍须针对本请求的Raw见证逐项验证。\n')
    add('终止状态完整分层：\n'+table(['阶段','路由','finish','条数'],[[k[0],k[1],k[2],v] for k,v in endings.items()])+'\n')
    add('v1/v2/v3准备版本未执行GPU：先补实际前缀校验、统一轮转，再修CPU预检日志重名。旧日志/空传输占位和失败保留；v4才实际推理。离线v4分析的单处compact/spaced JSON哈希比较错误由v5窄修复，AST证明其余分析完全一致；有效GPU单元无重跑、无覆盖。完整决策见 `ContractKV_Behavior_Scope_Repair_Decisions_20261020.md`。\n')
    add('## 8. 本轮能支持什么，仍不能支持什么\n')
    add('修复后的严格入口把模板授权、实际提交前缀和精确Raw行为证据连接在同一执行链。是否获得性能收益必须按上面各模型、重复及工作集条件判断；原Deployment的服务收益仍只支持其自身语义。旧36个下降、旧3456个compiled配对及本轮结果分别保留，不合并成统一安全率。\n')
    add('精确重复与轮转局部性是声明的服务条件；原384唯一输入/引擎的负载在此严格模式下应Raw，不会凭空获得摊销。此处没有测生产exact-query重复率，没有证明任意动态query/observation的Raw等价，没有解禁Repo或验证Llama新入口，也没有为新严格入口补开放到达Goodput。\n')
    add('统一cache salt/HMAC仍依赖可信入口和正确共享声明。哈希证明身份，不判断内容保密性；可信operator错误标共享仍是信任边界。时序侧信道、硬p99和完整多租户机密性不在本修复保证内。\n')
    add('## 9. 可复核记录\n')
    add('- 规则/输入：`protocol_v3.json`、`input_selection_v1.json`、两个inputs目录。\n- 冻结/预检：`development_freeze_v4`、`validation_freeze_v4`、对应实际preflight及Git byte audit。\n- 原包：`evidence_development_v1`、`evidence_all_v1`，每成员SHA；本地恢复后原成员未变。\n- 复算：`development_analysis_v5.json`、`validation_analysis_v5.json`、`all_local_independent_recompute_v1.json`。\n- 完整表：`final_descriptive_tables_v1.json`，含全部逐来源/逐重复/质量/费用。\n- 工具：`scripts/tsc_behavior_scope_analysis_v5.py`、`conformance_v1.py`、`report_v1.py`。\n')
    add('预定独立单元结束后停止本轮，不新增研究矩阵。正文与Response Letter均未修改。\n')
    with output.open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(p))
    print(json.dumps({'report':str(output),'status':'PASS','validation_quality':[q for q in quality if q['phase']=='validation']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.workspace,a.evidence,a.output)
