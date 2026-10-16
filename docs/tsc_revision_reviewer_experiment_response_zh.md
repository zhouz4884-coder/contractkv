# ContractKV 大修：逐条审稿意见与补强实验证据

更新日期：2026-10-16。状态：**实验回应工作版，`draft_with_placeholders`，不能作为已完成的正式 Response Letter 提交。**

本文按原大修信建立的 36 个意见 ID，记录已经做过的实验、结果、证据和仍缺的部分。保留编辑与 AE 要求，不虚构已完成的正文修改、页码、图号或作者信息。原信逐字文本和 SHA256 在本地保存；这里使用忠实的关注点概述。

最新执行状态（2026-10-16 22:19 后）：用户已明确继续自主推进。原版保真 R4 的 18 个三模型独立单元已在公开冻结后启动，仍未完成。开发对照的尾延迟代价继续保留；成本适配只依据此前 DEV，另立有界对照，不混入主 18。本文先保留已有证据，随实际完成情况更新。

## 当前证据的总体判断

- 已有实测：共同 HotpotQA 跨模型、自由生成审计、实际 512+ 长输出、完整成本与零 slack、D1/D2 拒绝与零发布、CacheBlend 配对分析、输入位移及复现审计。
- 已解决的具体工程问题：实际 Prompt/输出 IDs 记录、逐 token/EOS margin、线上单次认证、输入空白结构与 CODE_PREFIX 保真等。
- 仍需证据的核心问题：保真输入下，严格资格在新来源上的质量、覆盖和完整收益是否成立。四组 Qwen 开发对照不能替代这项验证。
- 可以明确写成限制而不继续增加 GPU 矩阵：未实现时间通道防御、可信运营者语义误声明、生产 query 重复频率未测、非普遍 p99 改善、Llama 224 项端点错误。
- 原稿 Table I 的两个具体百分比尚未闭合数据到 renderer/分母的来源链，不能宣称已复现。该问题保留在记录中。

## 证据索引

以下链接固定到已经核验的证据提交 `f8b5865fc987623a5618ab968afe8ad7ba46d75f`。归档及分析哈希证明可追溯性，不自动证明科学主张成立。

| 编号 | 证据 | 用途 |
| --- | --- | --- |
| C01 | [第一阶段总报告](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/docs/tsc_major_revision_phase1_summary_zh.md)；[共同 HotpotQA 来源簇区间](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r1/common_hotpot_shared_cluster_ci_v1.csv) | 三模型共同 scope、原预算及零 slack |
| C02 | [第二阶段总报告](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/docs/tsc_revision_phase2_summary_zh.md) | 准入修复、两批独立验证、保留反例 |
| C03 | [长输出修正报告](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/docs/tsc_revision_phase2_long_format_results_zh.md) | 三模型实际 512+ 成功条件及端点失败 |
| C04 | [原 R1 实验报告](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/docs/tsc_major_revision_r1_results.md)；[历史全成本重算](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r1/historical_full_cost_by_repeat_v1.csv) | 零 slack、D1/D2、CPU/live 边界 |
| C05 | [Manifest 案例](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r1/registration_manifest_cases_v1.csv) | 身份校验与可信误声明边界 |
| C06 | [Native-matched 质量阈值分析](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r1/matched_baseline_quality_thresholds_v1.csv) | CacheBlend 均值、改善、退化及公平比较 |
| C07 | [输入 token 位移](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r1/segment_token_displacement_summary_v1.csv) | 实际布局改变程度，不代表生产发生率 |
| C08 | [模板与行为 scope 审计](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/docs/tsc_revision_phase3_scope_amortization_audit_zh.md)；[实现语义审计](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r4/method_semantics_audit_v1.json) | 四项贡献、原部署与保守模式、摊销语义 |
| C09 | [R4 完整闭环质量表](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r4/validation_closed_v1/analysis/quality_summary_v1.csv)；[性能表](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r4/validation_closed_v1/analysis/performance_comparison_v1.csv) | 36 单元、三模型三重复、完整成本与尾部 |
| C10 | [全部 raw 重复控制](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r4/validation_closed_v1/raw_repeat_balance_v1.json)；[分数双向变化](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r4/validation_closed_v1/score_balance_v1.json) | 全路由/L0 变化与原生波动，不只报告下降 |
| C11 | [历史输入处理溯源](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/docs/tsc_revision_phase3_historical_input_audit_zh.md)；[保真开发对照诊断](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/docs/tsc_revision_phase3_fidelity_development_diagnosis_zh.md) | 真实任务适配缺陷、修复效果和残余 p99 |
| C12 | [R4 本地独立复算](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r4/validation_closed_v1/local_independent_recompute_v1.json)；[补充分析独立核对](https://github.com/zhouz4884-coder/contractkv/blob/f8b5865fc987623a5618ab968afe8ad7ba46d75f/results/tsc_revision_r4/validation_closed_v1/local_remote_independent_posthoc_match_v1.json) | 原始记录、来源及分析复现 |

## 编辑要求

| ID | 关注点 | 已做的工作与结果 | 当前状态 |
| --- | --- | --- | --- |
| E1 | 按期限提交修稿和逐点回复 | 已建立完整 36 项对应关系并保存实验证据；本文件是实验回应清单，不是已经提交的修回信。原信期限为 2026-12-13。 | 正文、正式回复与最终提交后置 |
| E2 | 完整稿件组成与作者简介 | 实验记录与稿件内容分开；没有编造作者简介或声称稿件已符合全部格式。 | 作者简介为 `AUTHOR_INPUT_NEEDED`；无须新增实验 |
| E3 | 补充材料/附录的提交方式 | 记录编辑要求单独文件，以及审稿问卷中对补充材料位置的不同表述。实验原始归档已分开保存。 | 最终包装时按编辑要求核对；尚未提交 |
| E4 | 修改标记方式存在不一致指示 | 保留 EIC 与 AE 对颜色标记的冲突，不把任何一种当作已经解决。 | 正文阶段形成干净稿与逐点定位清单，再核对提交格式 |
| E5 | 页数与期刊格式 | 完整证据独立记录，不因页数删除失败和成本。 | 压缩重复表述、排版与页数验收均未开展 |

## Associate Editor

| ID | 关注点 | 已做的工作与结果 | 证据与剩余事项 |
| --- | --- | --- | --- |
| AE1 | 组件创新与系统集成的关系 | 审计原部署模板、R1R、R2/R3、R4 的见证来源、scope 索引和发布分支。明确 R1R 开始的 raw 业务见证模式改变了行为资格语义，不能仅称原算法加了一个检查。R1R 与 R2 具体后端的 PASS 后发布分支 AST 一致。 | C08。保留四项贡献；不包装成双证书新系统。正文定位待改 |
| AE2 | 认证的必要性、自由生成、工作负载和开销 | 共同 HotpotQA 2430 配对；三模型均有独立声明的实际 512+ 成功条件；D1/D2 坏布局拒绝与零发布；完整成本和多阶段自由生成审计。R4 闭环 2442 个编译未来配对无 ID/分数下降，但全路由仍有 33 次 >0.03 下降。 | C01–C04、C09–C11。保真输入新来源验证仍待决策 |
| AE3 | 公平的基线解释 | 9000 个 native-matched 质量配对按每方法 2250 配对分析；同时报告均值、改善、退化和阈值敏感性。 | C06。不支持跨运行栈 2.18% 因果速度优势或 112 倍因果安全排名 |
| AE4 | Manifest、隔离和认证边界 | 完成 9 个 CPU 注册案例；7 个拒绝，合法声明及可信运营者错误语义声明可被接受。区分原有 live binding/PSTP 控制与未接入 endpoint 的 CPU helper。 | C05、C08。时间通道防御未实现；正文安全边界待写 |
| AE5 | 表述、相关工作和可复现性 | 源码/输入/模型/运行时身份、实际 IDs、原始归档、逐成员哈希和本地独立复算均保存。R4 补充分析还完成独立远端 CPU 核对。 | C07、C12。相关工作与正文修改后置，不以哈希代替有效性证据 |

## Reviewer 1

| ID | 审稿人关注点 | 我们做了什么、得到什么 | 尚不能声称或仍待完成 |
| --- | --- | --- | --- |
| R1.1 | 最高收益数字、92.90/92.62 的 scope 与分母 | 保留按模型、来源、协议、全路由/编译子集区分的表；补完整成本与实际覆盖。R4 三模型十租户聚合吞吐为 1.106/1.041/1.041×，不拿旧协议的高值概括新保守模式。 | 正文需统一摘要和主表口径；原 Table I 两组精确百分比来源链未闭合。C09、C11 |
| R1.2a | 用非 RULER 的相同来源做跨模型验证 | 相同 30 个 HotpotQA sessions、三模型三重复，共 2430 对；新 prefill 降低 Llama 38.38%、Mistral 40.69%、Qwen 48.05%。保留失败准入和 raw fallback。后续发现历史输入适配限制，已另做保真修复开发对照。 | 历史共同 scope 是其冻结协议下的正面证据；不能替代新保真输入、严格资格与完整成本的三模型独立验证。C01、C11 |
| R1.2b | 宏平均 CI 与模型间差异 | 以相同来源在模型间联合重采样，区分固定三模型平均效应与架构总体外推。零 slack 宏均值 5.242%，95% CI [-2.162,12.564]%。 | 该区间不是任意架构的预测区间，也不证明每个模型冷会话正收益。C01 |
| R1.3a | CacheBlend 与 ContractKV 跨栈比较公平性 | 按各自 native raw 基线计算配对变化，保留两条基线绝对质量；不把不同运行栈的速度差解释为单一方法因果效果。 | 正文需收紧比较结论；不是新增完全同栈 CacheBlend 重实现。C06 |
| R1.3b | CacheBlend 的退化频率及与原论文报告的差异 | 在 >0.03 阈值，CacheBlend 为 224 次下降、331 次上升，均分 0.333210→0.339817；ContractKV 为 2 次下降、0 次上升，均分 0.353780→0.353744。每方法 2250 配对。 | 不把个别退化与均值改善对立，也不把跨栈退化次数作因果安全倍数。原论文条件差异需在正文比较中准确说明。C06 |
| R1.4a | 认证之后自由生成是否真的保持行为 | 保存输出 IDs、首个分歧、任务分数、scope 和路由。历史编译 >0.03 下降分别为 R1 108/3672、R1R 2/8595、R2 7/5401、R3 3/4965；R3 三次来自同一 doc99 来源。R4 闭环 0/2442；保真 Qwen DEV 为 0/112，且该条件全部 360 对未来输出相同。 | 不同数据/规则不能组成因果风险下降曲线；全路由 R4 仍有 L0 下降；新保真独立验证未做。C01、C02、C08–C11 |
| R1.4b | 认证长度与实际较长输出 | 原预算保留，另设实际长输出条件。最终成功条件：Qwen 642、Mistral 769、Llama 578 tokens，各三个新进程重复、6 对未来 raw/compiled 正确。 | 使用完整自然 EOS witness；不证明认证前 64/96 tokens 能保证任意后缀。Llama 使用 192 项，224 项端点失败保留，不继续扩展长输出矩阵。C03 |
| R1.5 | Manifest 错误声明与安全边界 | 9 个 CPU 案例展示身份/所有权/字节不一致可拒绝，可信运营者语义误标仍可接受。 | Helper 未接入 live endpoint；哈希证明字节身份，不证明保密性。正文安全小节待写。C05 |
| R1.6 | 前缀缓存时序侧信道 | 已在实验记录中明确原型没有时间通道防御，不把授权共享或 P4 缓存状态隔离当作应用安全边界。 | 未做时间泄漏/防御实验；按审稿人允许的限制路径回应，正文与 Limitations 尚待加入 |
| R1.7 | 325000 次操作应区分 CPU 与 live GPU | 明确其为 CPU 状态机压力操作；真实业务生成、认证和 CPU 审计分别计数。 | 不能写成 325000 个 GPU 服务请求或在线效能证据。摘要文字后置。C04 |
| R1.8 | 小 KV pool 与数据中心适用性 | 保留原 2386-block 配置及注册 tenant/实际并发的区别。新 16K 运行另有每 cell 资源 manifest。 | 未新增数据中心硬件扩展实验；block 使用降低不等于释放相同比例 VRAM，也不把不同 pool 结果混比。C04、C12 |
| R1.9 | Raw fallback 和低覆盖应突出 | R4 逐来源、scope、拒绝原因和 L0 全部入账。Llama 十租户共同 L0 位置 2184 对，策略为 22 次上升/23 次下降；相同位置 raw 重复为 29 次上升/31 次下降，阈值 0.03。 | Raw 对照之间相关；不能因背景波动存在就宣布全部 L0 异常与策略无关。编译子集零下降不等于全路由零下降。C09、C10 |
| R1.10 | Table V 溢出 | 尚未修改正文排版，不虚构已修复。 | 纯排版事项，正文阶段渲染验收，无需 GPU |
| R1.11 | 用完整例子降低术语负担 | 已核对 compile/qualify/promote/reuse 与 scope 失效的实际路径，具备可复核代码和请求账本。 | 正文 worked example 未写，不声称已有新增图。C08 |
| R1.12 | 为补充证据腾出篇幅 | 实验证据独立集中，本清单可指导合并重复方法、协议和 scope 说明。 | 压缩正文、调整相关工作和表格均未实施，无需为此追加实验 |

## Reviewer 2

| ID | 审稿人关注点 | 已做的工作与结果 | 后续事项 |
| --- | --- | --- | --- |
| R2.1 | 清楚解释相对已有工作的进展 | 用代码审计区分稳定布局、行为准入、授权/生命周期和事务发布，避免把已知缓存原语都当新发明。 | 文献表与正文定位后置；C08 是系统实现依据，不替代文献检索 |
| R2.2 | 模型、任务与正式发表版本引用 | 实验模型/数据身份保存在 manifests；未把引用修订伪装成实验。 | 逐项核实论文/模型卡/正式版本，正文修改阶段完成 |
| R2.3 | 依赖和实现版本可复现 | 每 cell 包、native 扩展、模型、输入及源代码身份留存。本轮 manifest 为 Python 3.10.20、PyTorch 2.8.0+cu128、vLLM 0.10.2、transformers 4.55.2；实际 Prompt IDs 有独立核对。旧分析辅助说明中 remote Python 3.11 的文字标签已记录纠正，原结果不覆盖。 | C12。没有补造历史未记录的 Prompt IDs；CPU 测试不能冒充 GPU 接受性 |
| R2.4 | Artifact 链接改为脚注 | 已有公开源码、分片和复算证据，当前新增证据提交为 f8b5865。 | 论文脚注位置尚未修改 |
| R2.5 | 单项创新与集成创新分别说明 | 保留 CALC、Scoped Behavioral Certification、PSTP、Service-Template Certificate；明确保守 raw-reference 模式与原部署 attestation 的不同。行为资格 O(U)，固定 U 时按 tenant 摊销，不外推任意唯一 query 流。 | C08。没有新增第五项双证书或复杂预测算法贡献 |
| R2.6 | 量化输入重排程度 | 4695 个 segment 的实际冻结 tokenizer 位移分析已完成；补充实际 Prompt IDs 与物理前缀账本。 | C07、C12。位移不代表生产中这种布局的出现频率；原 Table I 精确数字仍有来源缺口 |

## Reviewer 3

| ID | 审稿人关注点 | 已做的工作与结果 | 边界与剩余事项 |
| --- | --- | --- | --- |
| R3.1 | 各任务 raw 顺序与真实应用依据 | 溯源 renderer，确认 1500 词截断和空白折叠跨历史队列；R4 中 HotpotQA 8/10 来源答案字面串因截断丢失，RepoBench 5/10 CODE_PREFIX 裁空、10/10 空白结构折叠。保真四组修复显著改善 raw 质量。另有固定版本真实应用 query-before-Sources 的代码依据。 | 字面串缺失不是语义不可回答的证明；应用代码顺序不是生产频率或原 Table I 数值依据。保真三模型新来源验证未做。C11 |
| R3.2 | 完整认证成本及零 slack | 重算四配置并新增真实服务完整时钟；新测净 TTFT 为 Qwen +17.50%、Mistral -2.84%、Llama +7.69%、14B TP2 +10.59%。R4/保真对照完整 wall 计入准备、首次 raw、失败认证、等待与日志/评分。 | 无法还原的历史参考/失败时钟仍标不可得；新四配置结果不能宣称精确重建原 Table III 全策略。闭环吞吐和固定到达 goodput 不混为容量。C01、C04、C09、C11 |
| R3.3 | 相对 D1 的价值及真正拒绝案例 | 两组各 20 个控制案例，均 10/10 坏布局拒绝、拒绝发布 tokens=0；14B 有真实后决策输出与 raw 分数控制。保留原 D1 goodput 1.472、D2 1.428 的比较。 | D2 的价值是行为准入和 fail-closed 发布，不承诺延迟超过已知安全 D1。无需再扩展 GPU 消融。C04 |
| R3.4 | 4.81× 点、区间、CPU 压力及 greedy 范围 | 分别保存负载点/协议/区间，实际服务业务与 CPU 操作分开；新结果保持 greedy、固定 seed 和模型配置。 | 不用后续小矩阵替换原负载点 CI；不声称采样解码或所有 p99 改善，正文应逐项收紧 |
| R3.5 | 补充相关服务、调度、安全与 SLA 引文 | 已把实验问题与文献问题分开，保留四项贡献和真实成本/尾延迟边界。 | 文献核实与正文增补后置；不新增与核心证据无关的 GPU 矩阵 |

## 正文与最终提交尚未完成的事项

本文件没有声称已修改任何正文。实验收口后，再给正式 Response Letter 填写真实章节、表格、图和页行位置；作者简介、引用版本、页数、表格溢出和标记冲突也在那一阶段核对。

用户已答复并授权当前自主决策，原版保真独立验证正在运行。成本候选及触发条件已单独记录于自主决策日志和有界成本适配计划；CPU 反事实分析不算 GPU 效果。只对有证据的局部缺陷作修补，不因小收益或不普遍的 p99 改善无限扩展研究。

## 中文核对

1. 此处的“完成”只指具体实验或分析，不等于全部第三阶段完成或论文可提交。
2. R1/R1R/R2/R3/R4 与保真条件的数据、规则、分母不同，不互相替换。
3. 任务分数改善与行为认证成功是两件事；相对 raw 一致也不证明回答绝对正确。
4. 所有负结果、原 L0 家族、部分固定到达单元、成本与未闭合来源均保留。
5. 本清单与总实验记录只用 Markdown；不生成 DOCX，不修改正文。
