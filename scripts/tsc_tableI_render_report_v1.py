"""Render the completed measurement record; never substitutes estimated results."""
from pathlib import Path
import csv
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'results/tsc_tableI_remeasurement_20261018'


def load(name):return json.loads((STUDY/name).read_text(encoding='utf-8'))


def pct(value):return f'{value:.3f}%'


def main():
    result=load('analysis_v1/summary_v1.json')
    integrity=load('analysis_v1/independent_integrity_v1.json')
    selection=load('input_independent_integrity_v1.json')
    aux=load('auxiliary_existing_six_source_v1.json')
    context_addendum=load('context_cluster_addendum_v1.json')
    context_stats=load('analysis_v1/context_cluster_stats_v1.json')
    context_by_family={r['family']:r for r in context_stats['summaries']}
    receipt=load('pre_forward_receipt_v1.json')
    assert result['execution_complete'] and result['all_requests']==3750 and result['future_requests']==3375
    assert integrity['status']==selection['status']=='PASS'
    assert not result['post_forward_parameter_changes']
    rows=[r for r in result['summaries'] if r['population']=='future' and r['family']!='ALL']
    assert len(rows)==5 and all(r['sources']==25 and r['requests']==675 for r in rows)
    lines=['# ContractKV Table I：独立测量完成报告', '', '日期：2026-10-18（香港时间）。本文件为实验与解释决策记录，不是 Response Letter。', '',
           '## 1. 完成情况', '',
           '已完成五家族各 25 个登记任务记录、每记录 10 轮、三次 fresh-process 重复：**3,750 个来源记录请求，3,375 个未来请求**。125 个记录对应 **114 组精确不重复的原始上下文**，不能称为 125 个独立文档。六个基础设施控制请求单独保留。没有替换记录或按结果改变参数。', '',
           f"事前注册提交：`{receipt['commit']}`；冻结 SHA256：`{receipt['freeze_sha256']}`。所有来源请求均晚于已核验远程提交的发布回执。", '',
           '原 Table I 五行数值的测量生成链仍未认证。此次提供的是独立的新测量，不将新旧数字接近视为旧统计来源已恢复。', '',
           '## 2. 五家族完整主结果', '',
           'Qwen3-8B / 原生 vLLM 0.10.2 / FP16 / 16K / max output 64 / 单活跃请求。每个来源开始前清空原生前缀缓存，十轮内保留。历史由真实先前生成答复和问题组成；检索文档不重复塞入历史。下面仅统计未来轮 1–9。', '',
           '| 家族 | 登记记录 / 原文簇 / 未来请求 | 稳定正文占输入 | 稳定正文原生恢复 | 全部原生命中占输入 |',
           '|---|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['family']} | {r['sources']} / {context_by_family[r['family']]['exact_original_context_clusters']} / {r['requests']} | {pct(r['stable_ratio_pct'])} | {pct(r['stable_native_recovery_pct'])} | {pct(r['all_native_hit_pct'])} |")
    mean=result['unweighted_five_family_future_mean_pct']
    pooled=next(r for r in result['summaries'] if r['population']=='future' and r['family']=='ALL')
    lines += [f"| 五家族等权均值 | 125 / 114 / 3,375 | {pct(mean['stable_ratio_pct'])} | {pct(mean['stable_native_recovery_pct'])} | {pct(mean['all_native_hit_pct'])} |", '',
              f"全局 token-pooled 值分别为 **{pct(pooled['stable_ratio_pct'])} / {pct(pooled['stable_native_recovery_pct'])} / {pct(pooled['all_native_hit_pct'])}**。它与五家族等权均值不同，二者均保留。", '',
              '三个指标分别采用：稳定正文 / 全部输入；实际命中的稳定正文 / 全部稳定正文；全部实际命中 / 全部输入。原生缓存命中的历史和框架 token 不会被改称为稳定正文恢复。', '',
              '### 来源簇不确定性', '',
              '原登记以 source_group_id 聚类；输入身份核查发现部分 ID 代表同一原文的不同题目。因此保留原 ID 簇区间，同时追加下列按原始上下文 SHA256 整簇 bootstrap 2,000 次的 95% 区间，保留同一原文的所有题目、重复及轮次。点估计不变，也没有丢弃重复文档记录。此聚类修正的理由、映射和时间另行记录；不冒充初始注册的一部分。', '',
              '| 家族 | 稳定正文占输入：95% 区间 | 稳定正文原生恢复：95% 区间 |',
              '|---|---:|---:|']
    for r in rows:
        corrected=context_by_family[r['family']]['original_context_cluster_95pct']
        a,b=corrected['stable_ratio_pct'];c,d=corrected['stable_native_recovery_pct']
        lines.append(f'| {r["family"]} | [{a:.3f}, {b:.3f}]% | [{c:.3f}, {d:.3f}]% |')
    legacy_path=ROOT/'results/tsc_revision_evidence_closure_20261017/tableI_lineage/lineage_audit.json'
    legacy=json.loads(legacy_path.read_text(encoding='utf-8'))['plot_source']['literal_constants']
    new_by_family={r['family']:r for r in rows}
    lines += ['', '### 与原稿记载的描述性核对', '',
              '旧列是历史稿件记载，未恢复测量依据。新旧 cohort、窗口与历史条件并未建立相同协议关系；以下不作差值的因果解释，也不以相近量级认定复现。', '',
              '| 家族 | 旧稿稳定比率（未核实） | 新实测 | 旧稿稳定恢复（未核实） | 新实测 |',
              '|---|---:|---:|---:|---:|']
    for i,family in enumerate(['RULER','HotpotQA','NarrativeQA','Qasper','RepoBench']):
        r=new_by_family[family]
        lines.append(f"| {family} | {legacy['stable_ratio']['value'][i]:.1f}% | {pct(r['stable_ratio_pct'])} | {legacy['native_recovery']['value'][i]:.1f}% | {pct(r['stable_native_recovery_pct'])} |")
    lines += ['', '逐重复数值、登记 ID 的 source-macro 值、warm 与 all-business 结果及原登记区间均在 `analysis_v1/summary_v1.json`；原文簇区间在 `analysis_v1/context_cluster_stats_v1.json`。所有主结果均报告，没有按是否接近旧数值选择家族或轮次。', '',
              '## 3. 实际历史与前缀边界', '',
              '完整性核查确认：每轮历史精确使用之前保存的真实生成文本；每个来源的稳定正文在所有轮次与重复中相同；原始问题、可选上下文保留部分和完整 CODE_PREFIX 在实际输入中保持。所有实际 Prompt IDs 均与完整渲染重新分词的结果相等。', '',
              f"实际命中达到离线无限驻留前缀上界的未来请求为 **{integrity['future_native_hits_equal_unbounded_prefix_bound']}/{integrity['future_requests']}**。这个上界只是一项离线诊断，主表的命中数来自实际 GPU 引擎返回值。", '',
              '下面完整列出全五家族的十轮描述统计，不挑选特定轮次来靠近旧表。这里按全部 token 汇总，不是五家族等权均值。', '',
              '| 轮次 | 请求 | 稳定正文占输入 | 历史占输入 | 稳定正文原生恢复 | 全部原生命中 |',
              '|---|---:|---:|---:|---:|---:|']
    with (STUDY/'analysis_v1/turn_profiles_v1.csv').open(newline='') as f:
        profiles=list(csv.DictReader(f))
    for r in profiles:
        if r['family']=='ALL':
            lines.append(f"| {r['turn']} | {r['requests']} | {pct(float(r['stable_ratio_pct']))} | {pct(float(r['history_fraction_pct']))} | {pct(float(r['stable_native_recovery_pct']))} | {pct(float(r['all_native_hit_pct']))} |")
    lines += ['', '轮次 0 为冷请求。历史增长能够改变比例，但这不能证明原 85.0% 就是由某个遗漏历史的旧实验产生。', '',
              '## 4. 输入、执行及保留情况', '',
              '- 固定哈希排序独立重建通过：125 个登记记录均等于事前规则选出的记录，没有按窗口检查或生成结果换样本。原文层面为 114 簇：RULER 25、HotpotQA 25、NarrativeQA 15、Qasper 24、RepoBench 25。',
              '- 与明确的旧排除记录核对原文后，NarrativeQA 的 25 条新记录及 Qasper 的 5 条记录具有此前出现过的上下文；不能将本轮宣称为全面未见文档泛化验证。它是独立登记的新执行/记录测量。此处不改样本，也不另外开启挑选未见文档的 GPU 矩阵。',
              '- 89 个来源保留候选池完整原文；36 个仅裁剪可选上下文：HotpotQA 14、NarrativeQA 17、RepoBench 5。系统原文、问题、完整 CODE_PREFIX 与保留区间的空白结构不变。',
              '- 三次进程均完成 1,250 个请求。所有输出保留，包括长度上限结束的输出；“完成”表示按登记预算完成生成，不表示任务回答正确。',
              f"- 结束原因计数：`{json.dumps(result['finish_reasons'],ensure_ascii=False,sort_keys=True)}`。本实验没有用任务分数筛选来源，也不提供绝对准确率或认证通过率。",
              '- 953 个登记 vLLM Python 文件在隔离 native overlay 中匹配 RECORD，全部 Qwen 模型/分词器/权重分片哈希匹配已冻结登记。原环境未改动。',
              '- 全部 raw IDs、文本、字符归属、真实命中计数、结束原因、源输入、协议、日志和摘要保留。主估计器及其 22 个冻结文件未改。', '',
              '完整候选池也已无损封存；其未压缩 SHA256 与首次来源推理前公布的哈希一致，可以重建抽样排序。新增完整性核查是运行期间记录的独立验证，不冒充事前主估计器。', '',
              '## 5. 写入前依赖核查的结论', '',
              '在 7 月 19 日完整表写入前，可见写作工具读过 manuscript、claim-evidence map、术语表、服务实验报告和协议；早先子任务读过缓存、质量、并发、经济性及服务扩展表。记录识别 317 次项目 Read 调用、280 个不同路径、116 个返回的 CSV 表头；其中存在读取错误，不能视为 317 个成功数据读取。', '',
              '**25 个来源/家族 × 10 轮有协议文件出处；原五行比例仍没有可认证的计数或计算输出出处。** 未找到对应指标计算的 Bash 动作。历史图像回执不包含像素，外部未保存记录也无法排除；不据此判断作者意图。', '',
              '详见 `docs/tsc_TableI_upstream_and_remeasurement_20261018_zh.md` 及 `upstream_v2/`。', '',
              '## 6. 六来源、三模型怎样强化动机', '',
              '已有六来源（HotpotQA 3、RepoBench 3）具有六组不同的原始上下文，且与新 125 个登记记录没有相同原文。它对应原有严格服务协议，应独立标注；三个模型不是 18 个独立来源。', '',
              '| 模型 | 来源 / 未来 raw 请求 | 登记稳定正文占输入 | 登记稳定正文原生恢复 | 全部原生命中占输入 |',
              '|---|---:|---:|---:|---:|']
    for r in sorted(aux['rows'],key=lambda r:r['model']):
        lines.append(f"| {r['model']} | {r['sources']} / {r['future_requests']} | {pct(r['stable_body_fraction_pct'])} | {pct(r['stable_body_recovery_pct'])} | {pct(r['native_total_hit_fraction_pct'])} |")
    lines += ['', '两组协议的历史、问题包装及登记稳定正文范围分别定义，不合并为一个共同均值。六来源结果与主服务实验更直接衔接；新五家族增长历史测量提供结构性广度，不代表这些历史变化已全部取得编译资格。', '',
              '## 7. 对正文与审稿解释的建议', '',
              '1. 保留 Table I 对结构性问题的论证位置和主线，使用可追溯的实际统计。六来源/三模型可以继续承担与主服务实验一致的主表；五家族独立结果可作另一分面或补表。',
              '2. 若新测量与旧数值处于相近量级，这支持相同现象，并不能认证旧五行或原来的生成过程。不要把抽样误差解释当作补齐缺失统计链。',
              '3. 回复时说明原统计链无法逐项恢复，因此提供源身份、完整输入 IDs、实际命中和固定口径的新测量；不把未认证的“早期快照”或“多轮历史原因”写成已知事实。',
              '4. 不将机会比例当作全部可获准编译覆盖，也不从本实验推导 ContractKV 加速或普遍质量保证。可实现收益仍由既有严格服务性能、行为审计与模板摊销实验支持。',
              '5. 本轮不修改算法或认证门槛，不开启后续大规模矩阵；正文和正式 Response Letter 的具体落笔在这些完整证据基础上安排。', '',
              '## 8. 记录与复算入口', '',
              '- 协议：`configs/tsc_tableI_remeasurement_20261018_v1.json`。',
              '- 数据根：`results/tsc_tableI_remeasurement_20261018/`。',
              '- 主结果：`analysis_v1/summary_v1.json`；逐请求：`analysis_v1/requests_v1.csv`。',
              '- 完整性与十轮：`analysis_v1/independent_integrity_v1.json`、`analysis_v1/turn_profiles_v1.csv`。',
              '- 原始记录：`cells/raw_native_r*/raw.jsonl.gz`、控制与完成清单、三份 worker log。',
              '- 复算与作用域：该数据根目录的 `README.md`。', '']
    output=ROOT/'docs/tsc_TableI_independent_measurement_completed_20261018_zh.md'
    assert not output.exists()
    output.write_bytes('\n'.join(lines).encode('utf-8'))
    print(json.dumps({'report':output.relative_to(ROOT).as_posix(),
                      'sha256':hashlib.sha256(output.read_bytes()).hexdigest()},ensure_ascii=True))


if __name__=='__main__':main()
