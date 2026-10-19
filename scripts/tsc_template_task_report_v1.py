"""Generate the final experiment MD only after exact local recomputation passes."""
import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path

STUDY=Path('results/tsc_template_task_serving_20261019')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fmt(value,digits=4):return f'{value:.{digits}f}' if value is not None else 'unavailable'
def interval(v):return '['+', '.join(fmt(x,6) for x in v)+']'
def table(headers,rows):
    return ['| '+' | '.join(headers)+' |','|'+'|'.join('---' for _ in headers)+'|',*['| '+' | '.join(str(x) for x in row)+' |' for row in rows],'']

def main(root,output):
    study=root/STUDY;proof=read(study/'formal_local_independent_recompute_v1.json')
    assert proof['status']=='PASS' and proof['actual_cells']==27 and proof['independently_recomputed_business']==10368
    data=read(study/'formal_analysis_v1/summary_v1.json');receipt=read(study/'formal_evidence_v1/package_receipt_v1.json')
    assert data['business']==10368 and data['actual_cells']==27 and receipt['sha256']==proof['archive_sha256']
    assert read(study/'formal_exit_v1.json')['returncode']==0
    protocol=read(study/'formal_protocol_v1.json');catalog=read(study/'development_catalog_v1.json')
    completed=datetime.datetime.fromtimestamp(read(study/'formal_exit_v1.json')['ended_epoch_s'],datetime.timezone(datetime.timedelta(hours=8)))
    lines=['# Task-Bearing Template Service Validation：第二阶段总报告','',f'GPU矩阵完成时间：{completed.isoformat(timespec="seconds")}（香港时间）。',
        '','本报告仅记录实验，不修改正文或Response Letter。完整27个fresh-server单元已结束，原始日志和全部不利结果保留；本地独立复算通过后才生成本报告。','',
        '## 1. 科学问题与实际保证','',
        '在固定问题、稳定文档及明确授权重复使用的服务对象中，Session与Template认证是否在同一Serving Stack、同一缓存授权组和完整冷服务时钟下，保留实际任务质量并改善资格经济性与SLO表现？','',
        '见证为原部署模式的compiled-path attestation：它校验该部署路径，不是任意未来请求的Raw等价证明。Raw/Compiled实际输出IDs、终止和任务分数由独立业务配对测量。全部内容来自真实HotpotQA/RepoBench任务；tenant/turn元数据和访问局部性为公开的受控协议，不能当生产trace或生产重复率测量。','',
        '## 2. P0与P1：冻结、开发、拒绝及授权闭环','',
        '新开发4来源、正式6来源，排除729历史/先前预留来源；所有新来源之间及与历史未发现完全相同的任务上下文，不能据此宣称语义独立。共同16K输入保留完整问题、CODE_PREFIX及原空白；超窗可选上下文按与gold位置无关的首尾规则裁剪，完整ledger保留。','',
        '三模型各52次开发生成，共156次。质量、物理命中及费用空间按事前双来源门槛判断，以下是家族级目录，并未根据正式结果解禁：','']
    rows=[]
    for model,entry in catalog['models'].items():
        dev=read(study/f'analysis_{model}_v4/summary_v2.json')
        rows.append([model,', '.join(entry['eligible_families']) or '无',dev['compiled_admitted_pairs'],dev['score_down'],
            '18' if model=='Qwen3-8B' else '9' if entry['eligible_families'] else '0'])
    lines+=table(['模型','通过开发的家族','开发attestation获准配对','全部开发>0.03掉分','正式单元'],rows)
    lines+=['Mistral的Repo与Llama的QA开发掉分均未删除；部署自路径认证通过不能代替Raw任务质量资格。所有Repo家族在正式服务中保持Raw fallback，Llama不进入正式矩阵。','',
        '三臂业务均经统一授权入口使用同一个模板缓存共享组；Session只改变证书对象及tenant绑定，不剥夺物理共享。canary在controller-private组生成，Session与Template均允许合法的canary缓存和certified-prefix读取。','',
        '## 3. Raw-only标定与完整服务时钟','']
    lines+=table(['模型','Raw-only速率 req/s','正式负载 req/s','TTFT/E2E SLO ms'],[
        [model,fmt(p['Raw_rate'],6),', '.join(fmt(p['Raw_rate']*m,6) for m in ([.8,1.] if model=='Qwen3-8B' else [.8])),f"{p['SLO']['TTFT_ms']}/{p['SLO']['E2E_ms']}"] for model,p in protocol['Raw_only_profiles'].items()])
    lines+=['速率与SLO仅由开发源Raw-only两个fresh-server、各80成功请求确定；阈值为1.5×本征请求p95、500ms向上取整、最低1500ms。没有用正式Contract结果选SLO或负载。','',
        '到达为相同标记Poisson轨迹：每模板两段32请求，共8tenant identity×8独立任务调用；不是8个并发GPU请求。客户端与GPU并发均为2。同一模型/重复的三臂在同一物理GPU执行，三重复Latin-square臂序。所有server ready后才开始测量，整波结束前不加载新模型。','',
        '全局服务epoch在准备与注册前开始，注册完成后不重置到达时钟。TTFT/E2E从原计划到达计算；完整wall包含准备、canary、注册、失败、绑定、业务与最终排空。模型/interpreter启动在client epoch外，单独保留日志。完整wall倍率不是固定到达条件下的最大容量加速。','',
        '## 4. P2：完整正式服务结果','']
    lines+=table(['模型/负载','策略','SLO达标/1152','绝对Goodput req/s','Mean到达TTFT ms','p99范围 ms','编译业务/1152'],[
        [f"{r['model']}/{r['load']}",r['policy'],r['total_SLO'],fmt(r['absolute_goodput'],6),fmt(r['mean_ready_TTFT_ms'],1),
         '['+', '.join(fmt(x,1) for x in r['p99_ready_TTFT_repeat_range'])+']',r['compiled']] for r in data['aggregates']])
    lines+=['以上按三个独立fresh-process汇总；Goodput为达标总数/完整wall总和。Mean按三个等规模单元汇总，p99保留重复范围，不承诺所有模型/来源尾延迟均下降。','',
        '### 同条件资格经济性与实际物理工作','']
    lines+=table(['模型/负载','策略','注册对象/真实RPC','Controller ms/business','业务新prefill','canary+验证额外新prefill'],[
        [f"{r['model']}/{r['load']}",r['policy'],f"{r['registration_objects']}/{r['RPCs']}",fmt(r['controller_ms_per_business'],3),
         r['business_new_prefill'],r['canary_plus_verification_new_prefill']] for r in data['aggregates']])
    lines+=['每个正式单元共有六模板，其中三个QA模板获前瞻资格；因此计划注册对象为Session24、Template3，8×对象摊销，不能照搬旧25tenant实验的25×数字。实际RPC、拒绝和费用如表。对象数减少不意味着GPU时间同比减少；两路都可读取合法已认证prefix。新prefill为真实初始引擎hit与prompt之差，不换算为GPU kernel时间。','',
        '### 配对增量与不确定性','']
    lines+=table(['模型/负载','比较','Goodput增量 req/s','三进程配对CI95','来源条件敏感性CI95','去一来源范围'],[
        [f"{r['model']}/{r['load']}",r['candidate']+' − '+r['reference'],fmt(r['absolute_goodput_delta'],6),
         interval(r['paired_three_process_bootstrap_CI95']),interval(r['conditional_source_sensitivity_CI95']),interval(r['leave_one_source_delta_range'])] for r in data['comparisons']])
    lines+=['仅有六个来源簇和三个独立进程。来源bootstrap/去一来源保持已观测整单元wall不变，属于组成敏感性，不能当重新改变工作负载后的反事实性能区间。tenant重复请求不当独立安全样本。区间跨零时，不把点估计写成稳健推广增益。','',
        '## 5. Raw配对质量与行为','']
    with (study/'formal_analysis_v1/paired_quality_v1.csv').open(encoding='utf-8',newline='') as f:pairs=list(csv.DictReader(f))
    quality=[]
    for model,policy in sorted({(r['model'],r['policy']) for r in pairs}):
        for subset in ['all','compiled']:
            rr=[r for r in pairs if (r['model'],r['policy'])==(model,policy) and (subset=='all' or r['compiled']=='True')]
            quality.append([model,policy,subset,len(rr),sum(r['IDs_and_finish_equal']=='False' for r in rr),sum(r['score_up']=='True' for r in rr),sum(r['score_down']=='True' for r in rr),sum(r['Raw_positive_score']=='True' for r in rr)])
    lines+=table(['模型','策略','子集','配对数','ID/终止变化','>0.03上升','>0.03下降','Raw正任务分数'],quality)
    if data['compiled_score_down']:
        lines+=['**本轮未建立编译子集零任务退化。** 所有已获准请求中的下降均保留在配对CSV，应按来源及重复定位；不能用速度或仅部署自路径认证成功掩盖。','']
    elif data['compiled_ID_or_finish_changes']:
        lines+=['已编译子集未观察到>0.03任务掉分，但存在ID/终止差异。可报告有限作用域内任务质量观察，不能写成严格逐token Raw等价。','']
    else:
        lines+=['已编译子集在本轮观测中未见ID/终止变化或>0.03掉分。它仍是有限、事前限定输入和访问协议的经验结果，不是任意未来query的保证。','']
    lines+=['全路由下降包含Raw fallback，不能删除或自动归因于编译。基线自身三重复与来源级记录可用于区分背景变化；不能仅因路由L0就宣布完全无策略关联。','',
        '## 6. 这批证据能支持什么','',
        '- 直接回答同栈、相同任务与授权局部性下的Session/Template费用差异；只根据实际对象、RPC及完整费用解释摊销。',
        '- 按冻结到达和完整成本评价TTFT与绝对Goodput；若只有费用优势而服务增量不稳健，就只主张模板经济性。',
        '- 结合Raw实际配对和原子发布回执/物理命中解释条件有效性；部署自路径认证与Raw等价始终分开。',
        '- 不修改原F8负结果，不把不同scope/来源/输入协议的倍率拼成因果曲线；不增加新算法贡献。','',
        '## 7. 原始证据、复算及保留失败','',
        f"完整原包SHA256：`{receipt['sha256']}`；{receipt['bytes']} bytes，{receipt['regular_members']}个成员，32MiB分片。",
        f"本地安全恢复后，{proof['independently_recomputed_business']}业务、27单元、完整summary和4份CSV逐字节一致；原始成员均未改变。",
        f"正式冻结SHA256：`{proof['formal_freeze_sha256']}`。所有角色真实输入IDs、计划时钟、任务评分、Native hit及HTTP验证次数按原记录核对。",'',
        '证据入口：`formal_protocol_v1.json`、`formal_analysis_v1/`、`formal_evidence_v1/`、`formal_local_independent_recompute_v1.json`。',
        '保留首次零输出启动依赖遗漏、Windows manifest路径预检失败、独立归档镜像漏收与修复记录；这些基础设施/CPU交付失败不冒充模型负结果，也没有通过重跑有效GPU单元消除。',
        '模型、tokenizer、runtime身份与epoch/授权组冻结；可信operator的语义误声明和时序信道仍不由HMAC/字节hash自动解决。本轮是内网可信controller实验，不声明公共IAM或完整多租户机密性。','',
        '预定单元结束后收口；不更换来源、负载、SLO或输出预算追求最高倍率。正文与Response Letter留待后续单独处理。','']
    assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True);output.write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    print(json.dumps(dict(status='MD_REPORT_WRITTEN',path=str(output),sha256=sha(output),requires_passing_exact_recompute=True)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
