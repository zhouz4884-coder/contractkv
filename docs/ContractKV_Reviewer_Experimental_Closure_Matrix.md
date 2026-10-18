# ContractKV：逐条审稿要求与实验闭合矩阵

2026-10-18。对照用户提供的原始大修信逐项整理，共36个编辑/AE/审稿子项。这里是**实验证据交付记录**，不是正式Response Letter，不填尚未定稿的页码/行号。

状态口径：**实证完成**表示所列具体实验或统计已验收；**限界回应**表示该意见允许或需要明确限制，而不是假装已实现防御；**进行中**表示仍有本轮冻结GPU单元未完成；**非GPU项**留到正文、引文与排版阶段。不能把某条实证完成写成整篇论文已可提交。

原始审稿来源：本聊天附件`2f909480-5ec5-4ee2-a885-4c3bb18edd75/已粘贴的文本.txt`。旧36项索引`docs/tsc_revision_reviewer_experiment_response_zh.md`保留为历史；其中“原TableIII待测”“Manifest仅CPU”“4.81×区间未恢复”等状态已由本文件更新。

## 证据入口

| 编号 | 实际证据及口径 | 文件入口 |
|---|---|---|
| F1 | 原TableIII同cohort新计时：24cells、12配对、4,725future pairs、525完整controller、453真实HTTP认证；A residual/B全controller零隐藏摊销/C直接完整wall分列 | `docs/tsc_TableIII_fullcost_replay_completed_20261018_zh.md`；`results/tsc_tableIII_fullcost_replay_20261018/analysis_v3/` |
| F2 | 三模型多类型行为与Manifest：9cells，720行为+135Manifest正式业务，另63失败；180候选、102实际变化全拒绝、30掉分全拒绝、78获准后0变化 | `docs/tsc_revision_mechanism_manifest_results_20261018_zh.md`；对应结果根`analysis_v3/`和`effects_v5/` |
| F3 | 实际GPU发布/后续命中与信任边界；27注册拒绝、18匹配compiled命中，可信operator误标9/9发布marker；跨域/旧epoch各18Raw仍原生命中 | `docs/ContractKV_Trust_Model_and_Enforcement_Boundary_Matrix.md`；F2原始证据 |
| F4 | 256-token等预算：3cells/240回答全部naturalstop、26获准后0变化；真实Repo：3cells/72回答，Qwen两来源L3实际9,712/3,328-token前缀命中，M/L输出契约早拒及length保留 | `docs/tsc_revision_budget256_results_20261018_zh.md`；`docs/tsc_revision_real_repobench_mechanism_results_20261018_zh.md` |
| F5 | TableI独立新测：125登记记录、114原文簇、三进程3,750业务/3,375future；五家族等权稳定正文94.144%、正文原生恢复0.595%。旧五行精确lineage未恢复 | `docs/tsc_TableI_independent_measurement_completed_20261018_zh.md`；`results/tsc_tableI_remeasurement_20261018/analysis_v1/` |
| F6 | 原RULER CI、92.90/92.62工作点、原Fig5 goodput CI均从已找回原请求重算，不能与新保真服务混合 | `docs/tsc_revision_remaining_work_audit_20261018_zh.md`；`results/tsc_revision_remaining_audit_20261018/` |
| F7 | 既有独立保真主18cells、R4完整36cells、CacheBlend native-matched质量分布、512+、位移与PSTP故障；各自原冻结分母/协议 | `docs/tsc_revision_reviewer_experiment_response_zh.md`的C01–C17索引及其原始结果；本文件不复测这些完成实验 |
| F8 | 新保真固定到达桥梁：新6源，7/7 Raw标定、840业务已完成；24正式+6隔离Gate尚未完成。CPU布局720/19,440segments、native/tail4,860future和两floor固定网格已完成 | `docs/tsc_revision_final_Raw_calibration_20261018_zh.md`；`docs/tsc_revision_final_serving_calibration_design_20261018_zh.md`；`results/tsc_final_existing_evidence_CPU_20261018/`；`results/tsc_task_faithful_open_arrival_20261018/` |
| F9 | 五家族实际raw顺序：从3,750已保存真实请求提取全部span/角色；旧R4另500 CPU渲染与新桥梁60 CPU渲染分列；Azure固定源码/许可证/SHA重新核对 | `docs/ContractKV_Five_Family_Raw_Order_Evidence_20261018.md`；`results/tsc_final_existing_evidence_CPU_20261018/raw_order_v1/` |

以下“质量下降”采用原报告阈值Δscore<−0.03，仍同时保存上升、不显著变化、精确输出ID和finish差异；0.03不是在线认证容差。重复租户/轮次不等于独立来源。RepoBench主评分是冻结的本仓库SequenceMatcher相似度，非程序执行或独立官方Levenshtein复现；正相似度不等于正确代码。

## 编辑要求与Associate Editor

| ID | 原要求/所需证据 | 实际处理与结果 | 证据 | 状态与剩余事项 |
|---|---|---|---|---|
| E1 | 按期限提交修稿及逐点回复 | 原信期限2026-12-13；实验、原始证据和逐项清单分开保存，未声称已经提交 | 原始信、本文 | 非GPU项：最终正文和Response Letter后置，提交确认邮件未产生 |
| E2 | 摘要、正文、引用、图表标题及简短作者简介齐全 | 不以实验材料替代正式稿件组成；用户要求作者简介约1/4页留位 | 原始信、现有V4稿 | 非GPU项：最终作者资料/排版验收，不能编造个人信息 |
| E3 | Supplement单独提交 | 原始数据与补充证据独立归档；保留审稿问卷与编辑说明的不同表述 | F1–F8 | 非GPU项：最终按编辑要求分文件，不为篇幅删掉不利结果 |
| E4 | 修改标记指示不一致 | EIC禁止彩色/粗斜体标修改，AE要求彩色标注；原文均保留 | 原始信 | 非GPU项：最终提交格式核对，不声称已解决冲突 |
| E5 | 页数、双栏模板与期刊格式 | 本阶段不为页数裁实验；现有稿件排版在实验后统一验收 | 现有V4稿、实验记录 | 非GPU项：图表、Supplement、作者简介与整稿页数检查 |
| AE1 | 区分组件创新与集成创新 | 已形成四机制的技术对象、接口约束、缺失反例、实测价值与费用矩阵。保留CALC/Scoped Certification/PSTP/Service-Template，不增第五项 | `ContractKV_Contribution_Necessity_Evidence_Matrix.md`、F2/F3/F7 | 核心实证完成；F8服务桥梁仍进行中。正文阐述后置，不能声称实现不存在的双证书自动切换 |
| AE2 | 认证超越重排的必要性、跨任务、自由生成与开销 | F2真实变化而非风险标签定义坏候选；F4补EOS预算/真实代码；F1计全部成功失败费用；F7保留共同HotpotQA、512+与严格自由生成 | F1/F2/F4/F7/F8 | 原三批完成；最终服务同协议质量/Goodput仍进行中 |
| AE3 | 不同运行栈的公平比较与一致解释 | 各方法相对自己的native baseline报告质量升降；不保留跨栈2.18个百分点因果速度或112×因果安全排名 | F7/C06、F6 | 实证完成；正文必须保留baseline非对称性及配置边界 |
| AE4 | Manifest正确性、隔离风险与认证范围 | 从9 CPU注册/19 binding检查，补到135实际GPU业务及提交/命中闭环；可信误标与Raw跨域命中均保留 | F2/F3 | 实证完成、限界回应；没有公网IAM或时间通道防御，正文安全小节待写 |
| AE5 | 清晰性、依赖版本、复现与相关工作 | 各新cell有冻结代码/输入/真实IDs、父模型/运行时身份、原始日志、独立复算和Git SHA；新Raw参数实际先公开后启动 | F1–F8、各归档回执 | 已完成部分均已发布；F8最终原始归档/复算和引用/正文尚待完成 |

## Reviewer 1

| ID | 原要求/所需证据 | 实际处理与结果 | 证据 | 状态与剩余事项 |
|---|---|---|---|---|
| R1.1 | 最高数字与近零D0不宜作摘要标题；解释92.90/92.62 | 追到92.9007%：D0/D2 mean TTFT2742.826/194.722ms，5进程×450future；92.62%：25tenant、80%load、三进程，852.354/62.908ms。前者TTFT均值不含registration，goodput分母计入。新F1完整wall四配置另列 | F1/F6 | 数字归因完成；摘要/结论应突出可比工作流和完整成本，不用D0=.066推统一21.5×。旧TableI未恢复链由F5新测支持现象，不能保留为已认证旧测量 |
| R1.2a | 在非RULER同一冻结范围跨模型验证 | 共同30 HotpotQA sessions×三模型×三重复=2,430未来配对，新prefill降低Llama38.38%、Mistral40.69%、Qwen48.05%。独立保真主18另有6源，Hotpot编译未来Qwen516/M342/L270，无ID/分数变化 | F7/C01/C13；F8 | 要求的共同非RULER实验完成；F8同协议服务证据进行中，不将模型/重复数当来源数 |
| R1.2b | 解释RULER宏平均CI为何窄于模型间差异 | 原30共同session、三固定模型宏均值86.67%，原CI[86.44,86.90]%从原数据复现；额外同步来源簇敏感性seed20261018/10,000 draws，CI[86.3204,86.9911]% | F6 | 实证完成；它是固定三模型平均的范围，非架构总体预测区间；原每模型90个process-session不是90个独立来源 |
| R1.3a | 跨运行栈速度比较不公平 | 明确保留各自native baseline、prompt计数与32-token chunk适配；撤去将差值解释为方法因果速度优势的依据 | F7/C06 | 实证解释完成；没有新增同栈CacheBlend重实现，正文需准确收紧比较 |
| R1.3b | CacheBlend退化率、作者条件及baseline非对称性 | 每方法2,250 native-matched配对；CacheBlend224下降/331上升，均分.333210→.339817；Contract2下降/0上升，.353780→.353744。分布、均值与报告阈值并列 | F7/C06 | 实证完成；本配置频率不当作原作者同条件复现，也不把平均质量和逐请求下降频率混为同一指标。配置/任务/阈值差异需在文字准确解释，不能声称112×因果安全优势 |
| R1.4a | 获证后真实自由生成分歧及任务代价 | R4闭环0/2,442 compiled future ID变化；独立保真主18为0/1,296。原R1/R1R/R2/R3及L0不利结果保留。新F2有78获准后0变化且全部102实际变化被拒；F4真实Repo另4获准后保持 | F2/F4/F7、F8 | 既有实证完成；F8正在将该检查与固定到达Goodput合并。有限观察不是普遍零风险；全路由L0差异不能删除或自动归为模型噪声 |
| R1.4b | 写明认证输出horizon，实际覆盖512tokens条件 | 自然EOS完整见证条件：Qwen642、Mistral769、Llama578tokens，各三fresh进程/6未来配对成功；Llama224项失败保留。新增256等预算240回答全自然结束 | F4、F7/C03 | 实证完成；不把64/96token证据外推到任意512后缀，不再无限扩展长输出 |
| R1.5 | Manifest应有注册检查、误配置案例、hash能检测什么 | 9CPU注册案例7拒绝、19binding检查17拒绝；新增27实际注册拒绝0候选提交；正确声明9前缀无marker，可信operator误标9/9发布含marker前缀。HMAC/hash只证明声明一致性/字节身份 | F2/F3 | 实证完成；需要正文独立信任小节，不声称语义保密检测或公网鉴权 |
| R1.6 | 加时间泄漏分析或明确不解决前缀缓存时间通道 | 本原型未实现防御；域授权和P4缓存状态隔离不消除域内hit时延推断。新增跨域/旧epochRaw命中进一步明确实际边界 | F3 | 限界回应：按原意见允许的限制路径，无需另起攻击/防御GPU线；正文须直说不解决timing channels |
| R1.7 | 325,000操作须区分内存状态机与live GPU | 保留CPU状态机分母；F1–F4的实际业务、RPC、失败另列。HTTP调用不等于kernel次数 | F1/F2/F4、F7/C04 | 实证分母完成；摘要/结论应移入CPU限定或删数字，不能写325,000个GPU请求 |
| R1.8 | 显著说明2,386-block pool、并发2及数据中心边界 | 原80登记tenant身份下530→149 allocator-used blocks约72%，不等于VRAM释放；新16K每cell原生pool/active/waiting另测。36新登记身份与实际最多2 GPU请求分开 | F7/C04/C17、F8 | 既有资源证据完成；F8实测资源仍进行中。未做数据中心规模硬件实验，不把80身份等同80同时执行请求 |
| R1.9 | Raw fallback占比、Llama/Mistral低覆盖与尾部须突出 | 全路由、compiled子集、拒绝原因、原家族L0、native驻留分列。历史R4全路由33下降、保真主18另4个L0下降保留；Raw重复只复现部分/背景差异，不唯一归因 | F7/C09/C10/C16/C17；F8 | 已有账本完成；F8来源/租户/请求级新尾部进行中，不以编译子集0事件冒称全路由0退化 |
| R1.10 | TableV frozen gate行溢出 | 属于最终PDF表格与列宽检查，不能靠GPU实验解决 | 原信、现稿 | 非GPU项：正文排版阶段渲染验收 |
| R1.11 | 早期完整请求例子减少术语负担 | F2/F3/F4已有真实compile→scope→PSTP→native hit/回退原始请求，可用于worked example；技术身份与物理前缀分开 | F2/F3/F4、贡献矩阵 | 实证材料已具备；图/正文示例与术语精简后置，不虚构自动协议切换 |
| R1.12 | 压缩重复segment/DAG/scope/协议与相关工作腾篇幅 | 以四机制对象及证据索引去重复；所有失败和成本仍放可复核记录 | 贡献矩阵、本文 | 非GPU项：正文重构与Supplement安排后置，不以扩实验替代删冗余 |

## Reviewer 2

| ID | 原要求/所需证据 | 实际处理与结果 | 证据 | 状态与剩余事项 |
|---|---|---|---|---|
| R2.1 | 相关工作前置、比较最接近系统、建立缺口 | 区分连续/跨位置复用能力与何时授权共享状态；贡献矩阵说明各组件对象和独立价值，不把所有缓存原语都声称新发明 | 贡献矩阵、F2/F3/F7 | 实证支撑已有；文献比较和引言重构非GPU事项，不能借外部论文效果替代自身结果 |
| R2.2 | 模型/任务引用和正式发表版本（如RULER COLM2024） | 模型、tokenizer、数据来源在frozen manifests可追踪；引用核实与数据/代码身份分开 | F1–F8 manifests | 非GPU项：正式版本、模型卡/任务引文在正文阶段统一核对，不声称已完成全部参考文献整合 |
| R2.3 | 关键依赖版本可复现 | 实际Python3.10.20、Torch2.8.0+cu128、vLLM0.10.2、Transformers4.55.2与native扩展、GPU UUID、模型资产和源码归档；新Prompt/Output IDs实际返回、独立核验 | F1–F8各freeze/runtime/独立复算 | 完成部分均可复核；F8最终归档待完成。旧客户端未保存IDs不重分词补造；不声称July环境逐字节复现 |
| R2.4 | Artifact网址改脚注 | 源、原始分片与独立复算已公开核Git SHA；网址位置是论文编辑事项 | 各结果目录归档回执 | 非GPU项：最终正文脚注修改后再按PDF定位 |
| R2.5 | 个体组件与集成的创新分别说明 | 四机制矩阵明确输入/输出对象、约束、反例、实测作用和费用；query-qualified成本O(U)，固定U时跨tenant摊销，与原部署模板O(1)不同 | 贡献矩阵、F2/F3/F7 | 核心实证完成；F8服务价值进行中。保留四贡献，不包装成新双证书架构 |
| R2.6 | 输入层的重排/位移量化 | 既有4,695个segment实际位置分析；新冻结6源三tokenizer、L0/L1/L2/L3共720布局/19,440segment，180个实际L0 ID锚点，依赖/16K边界核验 | F7/C07；F8/layout_v1 | CPU证据完成；不是GPU认证率、真实命中率或生产出现频率。正文/Supplement表格仍需正式嵌入 |

## Reviewer 3

| ID | 原要求/所需证据 | 实际处理与结果 | 证据 | 状态与剩余事项 |
|---|---|---|---|---|
| R3.1 | 五家族十轮raw中的mutable位置；真实服务顺序依据 | F5真实增长历史、实际Prompt IDs与native恢复；F9已从3,750实际请求交付五家族完整顺序，另将旧R4 500、新桥梁60 CPU渲染分表。Azure固定源码query-before-Sources只作应用代码例子 | F5/F7/F9、F8输入与CPU布局 | 顺序/结构实证已交付；尚需正式嵌入Supplement。F8新固定到达仍进行中；不把新表叫旧测量lineage恢复，不把源码用例当生产trace |
| R3.2 | 原TableIII加入完整验证费用/零slack对照 | F1完成24cells，A历史口径另列；B完整controller零隐藏TTFT降低L−.20/Q8 10.82/M2.00/Q14 20.93%；C直接wall L1.011551/Q8 1.020224/M.993820/Q14 1.109442。155非通过、30异常、60无RPC L0 warmup也计费用 | F1 | 原样本完整计费缺口已实测闭合；不是找回July缺失时间戳，不把B当C，也不说将原策略参数改成0。F8补服务Goodput正在进行 |
| R3.3 | 相对D1的收益及真正拒绝坏布局案例 | 同栈D1=1.472、D2=1.428req/s，治理保留约97%性能；旧两组各20案例和F2跨模型180候选提供实际拒绝、后决策生成与零新增拒绝发布 | F2/F3/F4、F7/C04 | 实证完成；D2价值是行为准入/治理，不能要求无条件超过已知安全D1，也不以近零D0倍率掩盖代价 |
| R3.4 | 4.81×仅80%load点、CI、325k CPU、greedy范围 | 从6个原cell重算500ms Goodput Raw .172667764→.830651232req/s，增量.657983469、CI[.538943295,.765225192]；比值4.810690862、CI[2.847508685,12.606992697]。固定cell wall/原bootstrap层次局限另记 | F6；F7 | 实证完成；仅该工作点，不代表整条负载曲线。325k明确CPU；当前所有认证/新服务为固定greedy，非采样保证；摘要/正文范围需后置统一 |
| R3.5 | 补服务/调度/KV共享攻击/SLA相关引文 | Vidur/RepoBench/Parrot等已用于问题诊断与任务定义核实；原信8篇建议逐项留待正式版本/相关性核对，不移植其性能作自身证据 | 原信、既有文献记录 | 非GPU项：文献与正文整合后置，不能将引用工作记为本系统实验完成 |

## 当前真正剩余的实验工作

1. 7个Raw已验收；正式390ea831已生成，预公开实际到达/SLO/执行版本与统计addendum后，运行24正式服务单元及6隔离Gate单元。
2. 验收相同协议中的自由生成、来源覆盖、真实物理命中、完整wall和Goodput；保留任何新反例或负收益，先归因再决定是否有必要局部修复。
3. 对全新服务结果进行来源/租户/请求级尾归因，完整原始归档、独立复算、Git远程SHA核对。
4. 将F8实际结果回填本矩阵、贡献矩阵、总报告与性能/尾报告；最后才安排正文与逐点回复定位。

没有计划为时序防御、生产exact-query重复率、采样解码或数据中心硬件另开研究线。这些是明确限制，不能靠零事件或短GPU测试伪装成已解决。
