"""Generate an outcome-bounded Chinese closure report from completed evidence."""
import argparse
import csv
import json
from pathlib import Path


def read_csv(path):
    with path.open(encoding='utf-8',newline='') as stream: return list(csv.DictReader(stream))


def f(row,key): return float(row[key])
def n(row,key): return int(row[key])


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join('---' for _ in headers)+'|']+['| '+' | '.join(map(str,row))+' |' for row in rows])


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    summary=a.root/'validation/summary'; long=a.root/'long_horizon/summary'
    audit=json.loads((summary/'completion_audit_v1.json').read_text(encoding='utf-8'))
    la=json.loads((long/'completion_audit_v1.json').read_text(encoding='utf-8'))
    if not audit['experimental_execution_complete'] or not la['execution_complete']: raise RuntimeError('Report requires completed audits')
    quality=[r for r in read_csv(summary/'quality_summary_v1.csv') if r['family']=='ALL']
    perf=read_csv(summary/'performance_comparison_v1.csv'); longrows=read_csv(long/'long_output_summary_v1.csv')
    controls=read_csv(summary/'raw_repeat_controls_v1.csv'); cells=read_csv(summary/'performance_by_cell_v1.csv')
    witness=json.loads((summary/'witness_decision_audit_v1.json').read_text(encoding='utf-8'))
    stages=[r for r in read_csv(summary/'observed_cost_stages_v1.csv') if r['family']=='ALL']
    lanes=read_csv(summary/'within_gpu_lane_diagnostic_v1.csv')
    drops=sum(n(r,'compiled_material_drops') for r in quality)
    compiled=sum(n(r,'compiled_pairs') for r in quality)
    paired=sum(n(r,'pairs') for r in quality)
    all_drops=sum(n(r,'material_drops_gt_0_03') for r in quality)
    routes=sum(r['scope_invalid_admissions'] for r in audit['cells']); pub=sum(r['rejected_published_tokens'] for r in audit['cells'])
    prefix=[r for r in perf if r['policy']=='query-prefix']
    lines=['# ContractKV 大修补强实验闭环报告','',
           '本报告覆盖原有七项补强要求，以及针对 R1 新发现问题的 query 范围修复。实验执行完成与科学目标是否达到分开判定；原投稿稿件没有被本实验包覆盖，修稿和逐条回复属于后续工作。','',
           '## 执行与证据','',
           f'- 原 R1：78/78 个 live 单元、25,650 次未来请求；本机复核通过，归档 423 个成员逐项哈希匹配。',
           f'- 新修复验证：{audit["complete_cells"]}/45 个单元、{audit["measured_futures"]:,} 次未来生成；三模型、五任务族、三次 fresh-process 重复。',
           f'- 长输出受控补测：{la["complete_cells"]}/9 个单元、{la["actual_generations"]} 次真实生成，其中 27 次 raw 参考和 108 次 raw/policy 未来生成。',
           f'- 新验证质量配对 {paired:,} 对，其中编译路由 {compiled:,} 对；scope-invalid admission={routes}，拒绝后发布 token={pub}。',
           '- 运行前冻结输入、代码和 backend 哈希；所有首次 raw、失败尝试与回退均保留。CPU 检查、机制控制、真实业务生成分别标注。','',
           '## 修复方法与实际质量','',
           '新 query 首次出现时先服务 raw，并用这次真实业务输出提供参考；随后只有该 query 自身通过验证的布局才可复用。验证器可以读取同 namespace/policy 中此前已批准、且仍实际驻留的稳定前缀；答案及 EOS 行仍全部检查。仅提取需要的 logprob 行，Transformer/KV 计算没有被省略成代理量。','',
           '这是受控修复变体：继承 family 最大级别并统一下降，检查答案/EOS 的 rank-one membership；辅助 margin/degradation 阈值设为宽界，未执行原论文的完整收益门禁。query-full 指全上下文验证计算，不代表复现原方法全部策略。因此新结果不替换原投稿的全工作流主表。','',
           '这也是保守的 query-catalog 模式：认证工作随不同 exact query 作用域的数量增长。fan-out 有意让多个 tenant 复用相同 benchmark 问题，不能据此推断生产中的重复 query 比例、任意新 query 的 O(1) 认证，或唯一 query 流上的收益；它与原投稿已资格化模板及其授权轨迹的结果分开解释。','',
           '以下总体分母同时包含首次 raw、冻结 L0 和验证失败回退。不同策略和两个场景有相关来源，不能把这些配对当成互相独立的样本。','',
           table(['场景','模型','策略','配对','编译','token 分歧 总体/编译','下降>0.03 总体/编译','编译最大分数下降','平均分 raw→策略'],[
               [r['study'],r['model'],r['policy'],r['pairs'],r['compiled_pairs'],f"{r['token_divergences']}/{r['compiled_token_divergences']}",
                f"{r['material_drops_gt_0_03']}/{r['compiled_material_drops']}",f"{f(r,'max_compiled_quality_drop'):.5f}" if n(r,'compiled_pairs') else 'NA',f"{f(r,'raw_mean_score'):.5f}→{f(r,'candidate_mean_score'):.5f}"] for r in quality]),'',
           (f'本次新样本中未观察到已编译请求超过 0.03 的任务分数下降（0/{compiled:,}）。这是本冻结范围的观测结果，不能外推为任意未来 query、工具内容或模型的零风险保证。' if drops==0 else
            f'本次新样本仍有 {drops}/{compiled:,} 个已编译配对超过 0.03 的任务分数下降。修复没有闭合全体行为风险，失败案例与来源簇必须继续保留。'),'',
           f'总体超过阈值的下降为 {all_drops}/{paired:,}；raw 路由上的事件也计入总体。分组案例与 raw 重复对照用于判断波动，不能仅因走 raw 就删除或直接免除因果责任。','',
           '对于已编译退化，诊断还核对未来输出是否与当初 raw 见证逐 token 一致。如果一致，说明证据可能只覆盖了当时的输出路径，不能据此证明不同私有元数据或批形状下的未来 raw 输出也相同。独立重复是否稳定、metadata 变化是否起作用，必须由相同输入的控制判定；单条退化不被直接归结为实现错误，也不被直接免除为数值噪声。','',
           table(['场景','模型','raw重复比较','token分歧','分数绝对差>0.03'],[[r['study'],r['model'],r['comparisons'],r['token_divergences'],r['score_abs_diff_gt0_03']] for r in controls]),'',
           '## 全成本与真实计时','',
           '单 session 与模板 fan-out 分开报告。fan-out 为十个模板、每模板十个 tenant session，并发仍为 2；这是闭环重放，不是 100 个同时活跃请求或开放环容量测量。完整 wall 包括 warm 业务、首次 raw、失败验证、准备和等待，不减去假想 tool slack。服务启动和独立预控制在各策略中同等排除。','',
           'readiness TTFT 从两请求 cohort 的上一 wave 完成屏障开始计时，包含其后的验证和派发等待；它没有测量各 tenant 在更早独立完成时即可就绪的延迟。完整 wall 保留了这些屏障等待。','',
           table(['场景','模型','策略','wave-ready均值 ms raw→策略','降低% [来源簇95%CI]','完整wall吞吐 req/s raw→策略','倍率 [三重复min,max]'],[
               [r['study'],r['model'],r['policy'],f"{f(r,'raw_ready_ttft_ms'):.1f}→{f(r,'ready_ttft_ms'):.1f}",
                f"{f(r,'ready_ttft_reduction_pct'):.2f} [{f(r,'ready_reduction_ci95_low'):.2f}, {f(r,'ready_reduction_ci95_high'):.2f}]",
                f"{f(r,'raw_full_wall_goodput_rps'):.3f}→{f(r,'full_wall_goodput_rps'):.3f}",
                f"{f(r,'full_wall_goodput_multiplier'):.3f} [{f(r,'goodput_multiplier_repeat_min'):.3f}, {f(r,'goodput_multiplier_repeat_max'):.3f}]"] for r in perf]),'',
           '置信区间对配对重复及来源模板重采样，tenant 和未来轮次保留在来源簇内；模型为固定模型，不能解释成模型总体预测区间。完整 wall 不被虚构拆成独立的每来源 wall，因此吞吐另报三次真实重复的范围。','',
           table(['场景','模型','策略','冻结GPU lane','raw/策略重复数','同lane吞吐倍率'],[
               [r['study'],r['model'],r['policy'],r['launcher_gpu_lane'],f"{r['raw_fresh_runs']}/{r['policy_fresh_runs']}",
                f"{f(r,'within_lane_goodput_multiplier'):.3f}"] for r in lanes]),'',
           'GPU lane 根据实际执行的冻结 launcher 任务序号恢复，并由每单元硬件快照提供运行背景；它不是另一套独立 device profiler。部分主配对跨两张3090，同lane表额外核对小幅收益是否可能来自硬件分配。每组重复数量较少且不等，不替代主估计，也不被包装成新的随机试验。','',
           table(['场景','模型','策略','wave-ready p99 ms raw→策略','后端请求 p99 ms raw→策略'],[
               [r['study'],r['model'],r['policy'],f"{f(r,'raw_p99_ready_ttft_ms'):.1f}→{f(r,'p99_ready_ttft_ms'):.1f}",
                f"{f(r,'raw_p99_backend_ttft_ms'):.1f}→{f(r,'p99_backend_ttft_ms'):.1f}"] for r in perf]),'',
           'p99 是合并三次独立进程重复后的观测分位数，不是独立请求假设下的总体置信区间。后端 TTFT 与包含验证等待的 wave-ready TTFT 各自保留，避免用更快的后端响应掩盖注册造成的尾部等待。','',
           table(['场景','模型','策略','验证总秒数','验证ms/未来请求','实际读取已批准前缀token'],[
               [r['study'],r['model'],r['policy'],f"{f(r,'verification_ms_total')/1000:.2f}",
                f"{f(r,'verification_ms_total')/n(r,'pairs'):.2f}",r['actual_prefix_read_tokens']] for r in perf]),'',
           '这是包含失败尝试的策略级总验证成本，按每个注册调用的完整耗时求和；并行调用可能重叠，不能再把它直接加到已经实测的 TTFT 或完整 wall 上。不同策略可能选择不同级别，故该表不被解释成同一 witness 的逐调用纯算子加速。独立冷读/前缀读控制检查判定一致性、错误 namespace/policy 和零拒绝发布。','',
           table(['场景','模型','策略','后端TTFT均值ms','首token后响应均值ms','输出token均值','其他注册准备ms/作用域'],[
               [r['study'],r['model'],r['policy'],f"{f(r,'mean_backend_ttft_ms'):.1f}",f"{f(r,'mean_after_first_token_ms'):.1f}",
                f"{f(r,'mean_completion_tokens'):.2f}",f"{f(r,'other_registration_ms_per_scope'):.1f}"] for r in stages]),'',
           '首 token 后响应时间仍含客户端/传输和结束处理，不能当成纯 GPU decode kernel 时间；其他注册准备是完整注册与逐次 verifier HTTP 时长之差，含渲染、tokenize 与控制开销。这些观测用来分析瓶颈，不被加回已经计入全部成本的 wall。输出长度同时列出，以免把生成长度变化的收益全部归因于 cache。','',
           f"真实任务还配对审计了 {witness['scope_registrations_compared']} 个 query 注册，其中 {witness['same_raw_reference_id_registrations']} 个具有相同 raw 参考 token 序列。相同参考下仍有 {witness['different_matched_level_decisions_with_same_reference']} 个同级判定变化；其中 {witness['same_reference_decision_changes_with_zero_prefix_read']} 个实际前缀读取为 0，{witness['same_reference_decision_changes_with_actual_prefix_read']} 个发生了读取。因此不能把全部变化归因于前缀读取，也不能把该优化称为逐位判定不变。缓存/重算及批形状造成的 FP16 排名差异是待检验解释，尚需固定输入的重复 cold/read 重放定位；本次没有据此调改 held-out 门禁。",'',
           '## 实际长输出与终止边界','',
           '原 R1 的 512 上限条件中，获准输出实际上均未超过 96 token，因此它不构成 512-token 正向行为证据。下面的独立受控任务要求输出完整整数数组，用 1536 上限允许自然 EOS 的较长输出；只按实际长度与结束状态计数。它不替代五任务族的正式任务评分或性能数据。','',
           table(['模型','上限','参考 length stop','获准参考','编译未来对','实际>512','编译最长token','分歧','正确数组 raw→策略'],[
               [r['model'],r['cap'],r['length_references'],r['admitted_references'],r['compiled_pairs'],r['compiled_outputs_gt512'],r['compiled_output_tokens_max'],r['token_divergences'],f"{r['raw_complete_correct_arrays']}→{r['policy_complete_correct_arrays']}"] for r in longrows]),'',
           '所有 length-stop 参考的发布门禁与实际未来输出均在长输出 completion audit 中核验；预算增大本身不被当成完成更长输出。','',
           '## 原七项要求的证据对应','',
           table(['要求','已获得证据','主要解释边界'],[
               ['非 RULER 共同跨模型','原 R1 三模型共同 HotpotQA：2430 配对；输入和固定 L2 完全相同','prefill 降低 38.38–48.05%；完整成本零 slack 宏均值 5.24%，CI [-2.16,12.56]%，不能称普遍冷会话获益'],
               ['认证后自由生成','原 R1 保留 changed-query 反例；新增 query-bound 实际 token/分数/回退/重复对照','新结果不回写原 R1，也不外推任意工具语义'],
               ['较长输出','原预算和 512 条件保留；新增独立真实长输出任务','受控长输出与正式 benchmark 质量分别报告'],
               ['完整成本与零 slack','四配置历史审计、真实零 slack D0/D1/D2、14B TP2 补测、新修复完整 wall','缺失的历史参考时钟仍标不可得；闭环与开放环结果分开'],
               ['D1/D2 安全消融','两组20-case guard；10/10真正坏布局被拒绝，拒绝发布0；补测实际后决策输出保持raw分数','D1是性能参考；D2的新增价值是行为准入和发布约束'],
               ['manifest与隔离','9例独立CPU声明/签名/所有权组件检查；另有live namespace/policy控制','CPU helper未接入live endpoint；可信operator误标私有内容不能由哈希发现；无时延侧信道防御'],
               ['CacheBlend、统计、输入','9000 native-matched 对照重算；阈值敏感性；4695 segment 位移；来源簇CI','不作2.18%跨运行栈性能优势或112x因果安全排名']]),'',
           '## 决策、限制与后续可证伪检查','',
           '原 R1 的新 query 反例支持收紧证书作用域，真实业务输出复用及 approved-prefix read 则针对完整成本来源。新正式矩阵保留冷会话与模板场景，使收益不足的场景不会被平均或摊销口径隐藏。','',
           '如果短 session 的完整 wall 仍不改善，一个待检验解释是新 query 数量、首用 raw 和级别下降成本超过该 session 内可节省的 prefill；本报告没有把它当成已证实的唯一原因。下一项检查应在新的开发输入上分解首次 witness、失败尝试、decode 和控制器等待，并在新冻结数据上检验收益门禁。','',
           'raw 路由的质量差异可能与 FP16、批形状或调度轨迹有关；必须结合相同输入与重复运行验证，不能仅靠路径名称归因。继承验证器检查每个答案/EOS 的 rank-one membership；并列最大分数和 teacher-forced/decode 的有限精度差异不构成唯一 argmax 或逐请求数学保证。','',
           '安全边界仍依赖正确的 operator 声明。授权和哈希不是机密性分类器，也不消除共享前缀时延推断；CPU 状态机压力操作不计为 GPU 服务请求。','',
           '原 R1 报告：`docs/tsc_major_revision_r1_results.md`。复现和计时边界：`docs/tsc_revision_r1r_reproduce.md`。原始数据、逐请求 CSV、运行快照及逐文件哈希保存在本实验 artifact。GitHub 的最终提交和清理审计由交付记录核验，报告生成本身不声称上传或投稿完成。','']
    known=a.root/'known_counterexamples'
    if (known/'completion_audit_v1.json').is_file():
        ka=json.loads((known/'completion_audit_v1.json').read_text(encoding='utf-8'))
        if not ka['execution_complete']: raise RuntimeError('Known-case followup is incomplete')
        ks=read_csv(known/'quality_summary_v1.csv')
        lines += ['## 已知失败的定向诊断','',
                  '这四个模型/来源单位根据原 R1 已观察到的失败选取，不计入新 held-out 成功率。每模型一个新进程，三种策略共享同一新 backend，固定顺序 raw→旧范围逻辑→新 query-prefix；共九个策略单元、108 次未来生成。旧范围客户端是受控适配，不是原运行栈或批形状的完整复现；这里不比较性能。','',
                  table(['模型','来源','策略','配对','编译','token分歧','下降>0.03 总体/编译','均分 raw→策略'],[
                      [r['model'],r['source_group'],r['policy'],r['pairs'],r['compiled_pairs'],r['token_divergences'],
                       f"{r['material_drops_gt0_03']}/{r['compiled_material_drops']}",f"{f(r,'raw_mean_score'):.5f}→{f(r,'candidate_mean_score'):.5f}"] for r in ks]),'',
                  '只有旧范围控制在此条件下确实再次退化、新路由保护了相同输入，才支持该反例的修复解释；若旧控制没有退化，应记录为未重现。新路由同时包含 query 绑定与允许级别下降，不能只凭这个组合对照把收益唯一归因于其中一项。原 R1 的全部失败记录继续保留。','']
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'report':str(a.output),'quality_pairs':paired,'compiled_pairs':compiled,'compiled_drops':drops,'scope_invalid':routes,'rejected_publication':pub}))


if __name__=='__main__': main()
