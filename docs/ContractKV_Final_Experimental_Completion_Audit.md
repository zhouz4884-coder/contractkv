# ContractKV 最终实验目标逐项验收

2026-10-19。目标来源为本聊天保存的 `goal-objective.md`，仓库镜像为 `docs/tsc_revision_final_strengthening_objective_20261018.md`。本清单区分**实验已执行、证据已验收、科学主张得到支持**三个层次。负结果完整交付可以完成某项实验，但不因此支持正向性能主张；文档存在、CPU接口通过或worker仍活着均不等于实验完成。

当前总体状态：**未完成**。前三批及两项有界补充已有原始归档和独立复算；主服务24单元已执行完成，最后隔离Gate六单元运行中。以下未验收项完成前，不关闭目标、不暂停跟进自动化、不宣布四份报告为最终稿。

## 一、实验与证据要求

| 目标要求 | 应验收的实际证据 | 当前状态与边界 |
|---|---|---|
| 继承已完成工作，不重跑、不覆盖旧冻结 | 历史freeze、保留的原单元SHA、失败/修复记录、当前唯一worker实际命令 | 前三批及主服务完成结果保留；只续查既有Gate worker。观察超时不作为重启理由 |
| TableIII四配置、三次Raw/Contract配对 | `tsc_tableIII_fullcost_replay_20261018/closure_v1.json`、`analysis_v3/`、24个completion | 已完成24单元、12配对、4,725未来配对 |
| TableIII全部成功/失败/异常/多级下降/无RPC控制器费用 | `controller_coverage_v1.csv`、`per_repeat_cost_v1.csv`、原请求与canary时间 | 已复算525个controller、453次RPC、155非通过尝试、30包装异常、60个无RPC的L0 warmup；不把RPC次数当kernel数 |
| TableIII A/B/C三个不同成本口径 | 同cohort新计时的residual-slack、完整controller零隐藏摊销、直接完整wall | 已分表交付；原2s/6s策略参数不改，C不抵扣slack，B不冒称C。旧质量下降保留 |
| TableIII物理工作、质量与原始缺失边界 | native totals、quality pairs、旧客户端记录能力 | 已交付；旧Prompt/Output IDs缺失不事后补造，不声称恢复July缺失时间戳 |
| 三模型五类型布局必要性 | 行为原文/IDs、Raw重复、未认证候选、认证决定、后决策路由、实际发布 | 已完成180候选、720正式行为业务；不是180独立来源。102个实际变化、其中30掉分全部由完整准入拒绝 |
| 每模型×类型的分母、错误准入、错误拒绝和费用 | `local_independent_effects_v5/observed_denominator_effects_v1.csv`的15个全候选类型行 | 已逐项进入总报告，162实际RPC与18个RPC前结束分开；所有行观察到的错误放行/不变拒绝/拒绝新增发布为0。零分母不定义拒绝率 |
| 原有Qwen8B/14B两组20案例对照 | 原D1/D2及Phase审计，不与新五类型重复并作来源数 | 既有证据复用并在审稿矩阵索引；新合成代码不代替真实RepoBench |
| 认证输出预算问题 | 独立256-token冻结、实际finish、240回答与后决策配对 | 已完成3单元，全部自然stop；保持原整数-only评分，不额外无限扩512 |
| 真实代码对照与任务契约 | 真实Repo3单元72业务、L0身份控制/L3、native前缀命中与输出 | 已完成；Qwen两来源实际L3命中9,712/3,328 tokens。M/L12个条件语法早拒且0RPC；Llama384-token length保留 |
| Manifest注册/绑定/认证/发布/命中分环节 | 9CPU注册、19CPU binding、135实际业务与native链 | 已交付，CPU结果不混入GPU业务分母；内部可信编排器边界明确 |
| Manifest角色/签名/版本/PRIVATE/MUTABLE冲突 | 注册与binding失败原记录、实际Raw fallback、候选提交 | 已交付；27注册拒绝0对应候选提交。部分字段控制为CPU检查，不伪装成每字段GPU攻击 |
| Manifest同域、改observation、改字节、跨域、旧epoch | 18同域compiled/full hit；不同内容/域/epoch各18实际控制 | 已交付；跨域与旧epochRaw仍能命中含人工marker前缀，compiled拒绝不等于Raw缓存隔离 |
| 可信运营者误标与时序边界 | 正确标注与误标各9条件，真实提交及后续命中；无防御声明 | 已交付，误标9/9发布marker。Hash/HMAC不证明保密性；不声称公网IAM或时序信道防御 |
| CALC布局阶梯 | 三tokenizer、六冻结来源、L0/L1/L2/L3，token/segment位移、DAG、完整渲染、block上限 | CPU证据已完成720布局/19,440 segments及180个实际L0 ID锚点；不是实际命中率或行为资格率 |
| Margin敏感性与doc99 | 固定网格和Raw/candidate两floor、旧0.40625反例原输入变化 | CPU证据已完成；离线PASS不等于新未来保证。未按新测试调margin或扩大scope |
| PSTP取消/超时/重复/冲突/回收 | 已有Phase16R/17/18实际native故障/提交记录，新增拒绝零发布 | 已有充分证据复用；没有重复GPU压力或真实共享未经认证状态 |
| 保真新来源独立选择 | 已知排除集、事前hash排序、输入/窗口/问题和CODE_PREFIX字节检查 | 已冻结并执行；新六桥梁源和另三真实Repo源精确字节不重复，不声称语义独立或原生RepoBench-C逐字复现 |
| Raw-only负载标定先于正式Contract | 7个Raw单元、840业务、实际参数派生与预公开回执 | 已验收；负载/SLO来自预定Raw规则，不按Contract收益选点。11700ms/435ms不是旧500ms工作点 |
| 正式Qwen两负载×三重复Raw/Contract | 12个真实fresh-server completion、实际到达/设备配对和阶段行为检查 | GPU执行与阶段检查完成；完整主分析/独立复算尚未验收 |
| 正式Mistral/Llama共同点×三重复 | 另12个真实completion与六个编译配对检查 | GPU执行与阶段检查完成；完整主分析/独立复算尚未验收 |
| 同预定到达、同调度和完整测量时钟 | 六条冻结轨迹、readiness TTFT/E2E恒等式、双请求wave、在线准备/失败费用及最终drain | 真实日志已生成；最终主分析逐请求验收待Gate结束后执行。双请求wave不是无限并发Poisson |
| 输出ID/finish、Raw绝对质量及双向分数 | 全业务实际IDs与冻结评分独立重算、compiled与全路由/Raw-repeat分开 | 主服务210/3888 future compiled阶段ID/finish检查0变化；覆盖低、来源少。全路由评分与跨模型双向统计仍待完整复算 |
| 主SLO Goodput与完整服务性能 | 预定到达TTFT和平均TPOT同时达标/完整wall；各进程绝对req/s与不确定性 | Qwen阶段数据已有；三模型统一主分析/来源簇敏感性仍待验收。现有wall约0.991–1.000×不支持整体加速 |
| 队列、GPU实际活跃请求、显存、KV容量与重算 | 原native事件、0.5s/2s采样、实际pool/block和原生计数 | 原日志已生成；全量对账待验收。缺字段保留None、采样峰值不是连续峰值、logical prefill不是GPU秒/全部重算 |
| Gate ON/OFF三对隔离真实消融 | 六个独立fresh-server completion；仅关经济分支，行为/EOS/PSTP保持 | 运行中。另一GPU空闲；没有隔离Raw基线，不借用主服务Raw算隔离speedup |
| Gate无效认证、覆盖、wall、Mean/P99与Goodput | 实际RPC及失败工作、获准scope后续复用、同到达ON/OFF全路径记录 | 待六单元完整结束及分析。不能把CPU开关接线或离线模拟写成真实筛除/排队效果 |
| 全局/来源/租户/请求层尾归因 | P99请求表、controller-to-submit、native等待、输出长度/EOS、前wave注册时间边界 | 既有54尾已按42 PASS/6失败RPC/5无RPC拒绝/1无注册纠正；新增服务全量分析仍待完成。只有duration时报告重叠上下界，不造唯一因果时间 |

## 二、交付与完成门槛

| 交付要求 | 当前证据 | 尚需完成 |
|---|---|---|
| A 总研究报告 | `ContractKV_TSC_Final_Experimental_Strengthening_Report.md`已有前三批、补充实验、历史统计及主服务阶段结果 | 回填Gate与完整服务统计、最终科学结论及可复核包入口 |
| B 四机制贡献矩阵 | `ContractKV_Contribution_Necessity_Evidence_Matrix.md`已逐机制列对象、接口约束、缺失反例、实测价值与费用 | 回填本轮服务/门禁的最终实测，不将弱收益改写为正向泛化 |
| C 逐条审稿证据矩阵 | `ContractKV_Reviewer_Experimental_Closure_Matrix.md`36个编辑/AE/审稿子项齐全；未完成项显式标注 | 验收F8并统一状态；正文、引文、排版和回复页行仍后置 |
| D 性能/尾延迟报告 | `ContractKV_Service_Performance_and_Tail_Analysis.md`按四类协议分开 | 回填实际Goodput、过程/来源不确定性、资源与Gate尾部归因 |
| Trust Matrix | `ContractKV_Trust_Model_and_Enforcement_Boundary_Matrix.md`含实际实施位置、失败动作、135业务与未覆盖风险 | 最终核验引用；不新增不存在的防御能力 |
| 前三批及两补充原始归档与独立复算 | 四个原包及本地复算回执已公开；TableI原请求和既有证据保留 | 不重复打包、重测这些完成数据 |
| 新服务原始证据及后验完整性 | 原始请求/IDs、native、遥测、源码快照和失败记录存在；冻结入口已公开 | Gate结束后运行主分析、预注册敏感性、integrity；同步新增CPU证据；打包/分片/双端逐成员核验 |
| 新服务独立复算 | Raw参数已从四原文独立重算；CRLF/浮点差异如实记录 | 从新原包恢复后独立复算正式30单元与敏感性，不仅重读summary |
| Git发布 | 所有完成批次及正式预注册已push并核远程SHA | 最终原包、复算、四MD及本验收清单push后重新核远程；不能以本地commit代替 |
| 决策和失败保留 | `tsc_revision_GPU_execution_decisions_20261018_zh.md`及各失败目录 | 补记新分析/归档异常或决定；不因结果弱就追加有利来源/负载/新算法 |
| 结束行为 | 当前目标和唯一跟进自动化保持active，正文/Response Letter尚未动 | 所有未验收项有实际证据后才完成目标并暂停该自动化；不能因文件齐全提前关闭 |

验收允许的结果是：说明哪些机制价值已得到实证支持，哪些收益只在特定工作区间成立，哪些新服务条件没有显著收益，哪些安全风险仍属于信任边界。它不允许将“没有找到新错误”替代对完整费用、质量和可复现交付的正面核验。
