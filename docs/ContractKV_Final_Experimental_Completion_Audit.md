# ContractKV：最终实验逐项验收

2026-10-19。**实验、原始归档与本地独立复算完成；不再启动GPU。** 本验收对应final_strengthening_objective，不是正式稿件就绪或已提交声明。远程交付以Study/final_publication_receipt_v1.json实际核验的commit/blob为准。

## 1. 科学与执行要求

| 目标要求 | 实际验收证据 | 结论及边界 |
|---|---|---|
| 继承已有运行，不覆盖旧freeze/结果 | 原三批、R1–R4、成本适配及部分到达试验各自保留；新批独立目录和SHA | 完成；不把旧/新协议混作同一主实验 |
| TableIII四配置×三重复Raw/Contract | 24cells、12配对、4,725future、525完整controller/453RPC | 完成；155非通过、30异常、60无RPC warmup均计费 |
| residual-slack /零隐藏摊销 /直接wall分开 | TableIII analysis_v3、独立成本复算与完成报告 | 完成；策略2/6s原值不改，B与C不混，July缺失时间戳未恢复 |
| TableIII质量、长度、实际计时 | 全部请求/费用/异常保留；Qwen旧compiled次级.72→.38保留 | 完成；旧客户端缺完整IDs仍是限制，不重分词伪造 |
| 三模型五类型真实候选与后路由 | 180候选、720行为业务；102实际ID/finish变化全拒、30掉分全拒、78获准后0变 | 完成；18候选在GPU RPC前结束，不全写成GPU verifier拒绝 |
| 各模型×类型实际分母/费用 | 15行effects_v5，每行12候选；Raw重复、任务升降和完整controller | 完成；风险标签不等于实际变化，0/0不写100% |
| 拒绝候选零新增共享发布 | 行为/Manifest真实PSTP提交与native块链、既有故障/取消/超时/重复/回收 | 完成；不是整个Raw缓存清空或所有并发形式证明 |
| Manifest注册→绑定→真实KV闭环 | 135实际业务/18RPC、27注册拒绝、18合法后续完整命中、72后续控制 | 完成；CPU9/19检查单列，不冒充GPU隐私防御 |
| 可信误标/跨域/旧epoch | 误标9/9含marker发布；跨域与旧epoch各18 Raw原生命中marker | 完成且不利结果保留；内部可信控制器，非公网IAM/时序防御 |
| 等预算完整终止补充 | 256条件3cells/240自然stop，26获准后0变化 | 完成；非任意长输出保证，不自动追512 |
| 真实Repo而非仅合成代码 | 三盲选项目/三模型72业务；Q两来源9712/3328token实际命中，M/L12语法早拒 | 完成；chat适配/SequenceMatcher，非原版RepoBench-C逐字复现 |
| 新服务源独立选择与输入保真 | 排除已知来源后hash排序，新六源及另三Repo原文byte-disjoint；16K问题/CODE_PREFIX/空白审计 | 完成；精确不重复不等于语义独立 |
| Raw-only标定先于Contract结果 | 7cells/840业务，派生负载/SLO与pre-forward Git回执 | 完成；TTFT11.7s/平均TPOT435ms不与旧500ms混合 |
| Qwen两负载×三配对 | 12fresh-server cells、同到达/设备与r2次序平衡 | 完成；Qcommon/high wall .999986/.990905×，不承诺加速 |
| M/L共同负载各三配对 | 另12cells，合计主24/8,640业务 | 完成；wall .999372/.999568×，不是数据中心容量 |
| 全在线费用与固定到达clock | 实际readiness/backend/E2E/最终drain、目录展开clock边界、完整controller/RPC账 | 完成；外部两请求wave仍保留，无限并发/异步协议未实现 |
| SLO绝对Goodput和统计 | 四组Raw→CT达标761→764、46→82、332→338、491→494；10,000来源/过程敏感性 | 完成；四组绝对差区间跨0，Qhigh241次分母0导致ratio CI留空 |
| 实际IDs、见证和绝对质量 | 主210/3,888 compiled future对Raw/见证0变；Q参考正分54/54，M0/54/L0/48 | 完成；新M/L获准QA不能承担有用答案正证据 |
| 全路由升/降与Raw重复 | 主Q两负载13升5降/14升6降，M/L有ID变化；完整Raw重复/finish/length表 | 完成；不将所有L0变化唯一归因背景噪声 |
| 物理命中/prefill/驻留 | Q每load compiled全业务39full/27zero，M66full，L42full/6zero；实际native与逻辑新token账 | 完成；资格≠驻留，logical token≠GPU秒或全部重算 |
| 客户端队列/GPU活跃/资源 | 实际offset重建pending、native active≤2/waiting≤1；2秒VRAM采样/pool与计数 | 完成；客户端积压与GPU等待分开，采样非连续峰值；preemption0不等于APC eviction0 |
| Gate ON/OFF真实三配对 | 六cells各1,080业务/972future；54决定完全同、21RPC/18失败/54compiled future各相同 | 完成，中性；无观察筛除，wall .999991×，Goodput差区间跨0；无隔离Raw基线 |
| 新旧tail逐请求归因 | 旧54=42PASS/6失败RPC/5无RPC拒绝/1无注册；新主96全L0/38length/88Repo | 完成；新仅1即时前注册约1.721ms，不能把全部长尾归因失败认证，也不排除历史传播 |
| CPU CALC阶梯与位移 | 720布局/19,440segment，三tokenizer/180实际L0锚点；既有4,695位移记录 | 完成；结构上限不是GPU行为或命中证据 |
| 固定margin网格与scope | 0/.03125/.0625/.125/.25/.5/1、两floor；doc99 .40625案例 | 完成；提高margin不代替ScopeValid，不按held-out调门槛 |
| TableI/原CI/服务点/顺序 | 125登记/114簇、3750业务；五家族raw顺序、原RULER CI/92.90/92.62/4.81点CI | 完成；旧TableI精确lineage未恢复，不认定旧数编造或声称恢复 |
| 37单元后验完整性 | post_execution_integrity：11,640业务/22waves/58Root/564快照，模型size/mtime吻合原完整SHA | 完成；未重复全权重hash或共享runtime复制 |

## 2. 原始交付与独立复算

| 验收 | 真实回执 | 状态 |
|---|---|---|
| 四个早期批次原包/失败/版本 | TableIII、机制Manifest、256、真实Repo各local_archive_verification与local_independent_recompute | PASS，完成数据不重打包/重测 |
| 新原包完整性 | ce8a001e246f04012d56276232ad2b4acb706149dfde60d0155473e649320cfc；4parts、234884895bytes、1246成员、58Root | local_archive_verification PASS |
| 新原始包科学独立复算 | local_independent_recompute：37cells/11640业务，formal6891/calibration934叶，敏感性135叶精确，13CSV字节相同 | PASS；summary JSON仅换行不同，LF归一精确；0GPU |
| 原证据重算后不变 | 再核全部1246成员SHA，与原inventory相同 | PASS；不改原summary、评分、轨迹或IDs |
| 失败与基础设施修复 | 原端口/AST/EOS、CPU浮点/换行、打包遗漏5Root修复与旧源postimage、失败传输等 | 保留，不按结果删样或重测完成cell |
| 决策范围 | 用户要求停止剩余Gate时原六cells已自然结束，无在跑任务需终止 | 真实记录，不伪造取消；此后0新GPU |
| Git最终交付 | final_publication_receipt_v1.json核数据/四MD/代码的实际commit与blob；receipt由后续commit发布 | 按实际receipt验收；不以本地commit/文件存在替代远程SHA |

## 3. 交付文件及非实验剩余工作

A总报告、B四机制贡献矩阵、C审稿36子项证据矩阵、D分协议性能/尾报告与Trust矩阵齐备。C保留编辑/引文/排版未完成状态；它不是正式Response Letter。每项证据可定位原始结果或独立复算回执，不能只引用助手叙述。

本阶段实验问题已得到可核查答案，包括不支持预期的结果。尚未证明普遍跨来源SLO改善、零风险自由生成、任意动态query的O(1)认证、可信误标检测、引擎级Raw隐私或时序防御。它们不作为无限扩GPU的理由。

后续按用户既定顺序：先整合正文和图表/补充材料，准确呈现原部署与严格保真协议的贡献和边界；再写英文Response Letter及页行映射。正式稿/引文/作者资料/版式/提交均未由此验收。实验目标的完成以最后Git发布回执为准，完成后暂停本轮实验自动跟进。
