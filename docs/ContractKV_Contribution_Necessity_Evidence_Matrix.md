# ContractKV：机制贡献、必要性与实证对应矩阵

2026-10-18。本文件记录四项原有贡献的技术对象与独立证据；Raw7/7与主服务24/24 GPU已完成，Gate6运行中，完整统计/独立复算/归档尚待完成。本文不是 Response Letter，也不修改论文中的性能主张。

共同研究命题：**将重复内容转化为共享 KV 服务状态，需要同时约束布局、行为资格与状态可见性。** 物理字节重复、见证资格和发布后的驻留分别由不同证据验证，不能互相替代。

## 四项技术对象及其必要性

| 机制 | 技术对象与输入/输出 | 必须保持的约束 | 去掉该机制会缺什么 | 独立实测价值 | 实际费用与限制 |
|---|---|---|---|---|---|
| CALC | 带 segment 类型、稳定性声明和依赖边的 Prompt 表示；输出合法拓扑顺序、布局档位及实际渲染后的稳定前缀边界 | 保持已声明依赖；原任务关键问题/CODE_PREFIX 与空白结构不丢失；用完整实际 tokenization 确认前缀，不能用各段 token 数简单相加代替 | Native APC 只能恢复开头连续相同的 token；动态段在前会遮挡后面的重复稳定内容。单有认证/签名不能把非连续内容变成可查找的物理前缀 | 新冻结 CPU 阶梯审计覆盖 720 布局、19,440 个 segment；真实 Repo Qwen L0 身份控制只提交/命中48-token前缀，L3 两来源实际提交/命中9,712和3,328 tokens，后续输出保持。保真跨模型主验证另有实际 native 命中与新 prefill 账本 | CPU 编译/HTTP 准备计入完整服务时钟。合法性只相对于输入 DAG；未编码的顺序语义不会凭空被推断。Token 前缀上限不是行为资格，也不是实际驻留量 |
| Scoped Behavioral Certification | Raw 实际生成见证、候选逐 token/EOS 检查与作用域绑定的资格决定；输出 PASS/FAIL/INCOMPLETE 和证据 | 当前模型/运行时/生成配置、布局与输入作用域匹配；完整自然终止见证；原 raw/candidate margin floor 不放宽；证据不足走 L0 | 依赖合法不等于自由生成保持。布局仍可能改变指令优先级、证据位置、tool解释或终止行为；单次 margin 通过也不能授权未覆盖的动态输入 | 三模型180个受控候选中，102个实际 ID/finish 变化全部拒绝，其中30个真实掉分全部拒绝；78个不变候选获准，后续0变化。180个 Raw 重复稳定。真实 Repo 的 M/L 候选变化另被现有输出契约早拒，不能冒称它们经过 GPU verifier | 原受控诊断中全资格 controller 均值 Qwen323.651、Mistral256.712、Llama204.195 ms/候选；这是短输入、诊断 hook 下的费用，非服务加速。严格 query-qualified 成本随获选唯一 scope 数 U 增长；不把它写成每模板一次 O(1) |
| PSTP | 候选事务状态与 prefix-selective promotion：将私有候选的 PASS 与共享块登记相连；提交长度为完整 block 边界 | 只有证据支持的 PASS 可以提交；长度不超过已确认稳定边界和实际计算边界；FAIL/INCOMPLETE/CANCELLED 不新增候选共享发布；重复/故障路径保持生命周期约束 | 即使 verifier 做出了拒绝，若候选在拒绝前已成为共享 APC 状态，后续请求仍可能读到未获准的块。只记录一个“拒绝”标签不足以证明状态不可见 | Phase16R/17/18 已有真实 native 故障、取消、超时、重复提交与回收控制；本轮180候选中全部拒绝的新增发布 tokens 为0。Manifest匹配18/18后续请求完整命中已提交前缀，native block-hash链相符 | 发布操作及失败处理计入 controller/完整 wall；不以CPU状态机325,000操作代替GPU测试。零发布仅指被拒候选新增共享状态，不指清除整个引擎已有Raw APC。已有证据不是所有并发交错的形式证明 |
| Service-Template Certificate | 对共享服务状态进行身份/授权/版本/生命周期绑定的模板资格对象：模型、tokenizer、runtime、generation、policy、manifest、layout、stable-prefix、authorization domain及epoch相联系 | 资格仅在声明域与生命周期内复用；query资格身份与物理stable-prefix身份分开，允许不同已获准query指向同一物理前缀；可信operator负责共享内容语义声明 | 没有模板共享与身份治理，会按会话重复承担资格和状态管理费用；即使字节相同，也无法仅凭hash决定是否授权共享或何时失效 | 原受控Session/Template实验：验证调用125→5，未隐藏认证成本25.05→3.24ms/request；同栈D1安全布局1.472、D2完整治理1.428req/s，保留约97.0%性能。新增Manifest实际135业务闭合注册/绑定/发布/后续命中 | 25×调用摊销与约7.7×每请求未隐藏费用优势限于该授权重复服务协议。新query保守见证模式按U摊销，不与部署模板O(1)混同；生产exact-query重复率未测。签名/HMAC是可信内部控制器检查，不是公网IAM或内容保密分类器 |

## 三种身份不能合并

1. **资格身份**说明“哪个行为见证、作用域与环境配置支持哪个候选”。历史 NarrativeQA doc99 的候选 margin 0.40625 仍可通过旧见证，未来 Raw 因输入变化而改变，说明更高 margin 不能替代作用域条件。
2. **物理前缀身份**说明“完整 Prompt IDs 的哪个连续前缀可以对应相同 KV 块”。同一资格目录可以关联多个前缀，多个合法 query 也可能关联同一个前缀；不能按资格数推断物理缓存对象数。
3. **当前驻留身份/状态**说明“此时 lookup 是否实际命中、命中多少”。登记过hash或签发过资格不保证一直驻留；已有保真实验中确有 compiled 请求部分命中或零命中。必须看 native lookup/块链，而不是从证书存在推出节省。

这解释了为何本系统的价值不是仅把 Prompt 重排、签名、缓存三者并排放置：布局决定可被恢复的连续对象，行为资格决定它是否有本次证据支持，事务决定其何时能被后续请求看到，模板对象决定谁能在什么环境/版本下复用并分摊费用。这些接口之间的约束是实验需逐项验证的对象。

## 哪些结果真正支持必要性，哪些不支持

- **D1/D2**：D1是已冻结安全布局，没有治理的额外成本；D2的合理价值是行为准入、零拒绝发布、生命周期和跨租户摊销，不能要求它在每个安全布局上无条件比D1更快。D0极小基线不用作突出创新的倍率标题。
- **受控有害候选**：风险标签不是行为变化结果。102/180来自实际输出ID/finish差异；Mistral15次、Llama6次未认证候选升分仍保留。认证不以选择高分候选为目标。
- **256 tokens**：240次全部自然结束，26个获准后无变化，表明两例64-token截断可以在该独立预算条件结束；不证明所有长输出或任意后缀安全。
- **真实Repo**：Qwen的L3物理命中证明实际结构复用，4次获准后无变化证明这几个受控请求的行为保持；M/L的12个条件在语法保护处早拒，0GPU认证RPC。不能将后者并入GPU拒绝率，也不能将SequenceMatcher正分当作程序正确。
- **Manifest误声明**：显式PRIVATE/MUTABLE等27次实际拒绝与零候选提交有独立价值；可信operator语义误标9/9仍发布人工marker，是必须保留的信任边界。不同授权域/旧epoch各18次compiled拒绝后，Raw仍命中含marker前缀，不能声称引擎级隐私隔离或时序防御。

## 性能证据的协议分工

| 协议 | 能回答的问题 | 当前证据与状态 |
|---|---|---|
| 原部署模板、工具slack条件 | 已获准模板的共享服务价值与可隐藏认证成本 | 原TTFT/SLO、Session/Template125→5调用、授权tenant扩展结果保留，各自按原负载和分母报告 |
| 原TableIII同样本完整计时重测 | 原在线资格和失败费用全部计入后实际还省多少 | 24/24完成；直接wall Llama1.011551×、Qwen8B1.020224×、Mistral0.993820×、Qwen14TP2 1.109442×。策略2s/6s没改，完整wall不抵扣slack；A/B/C不同口径分开 |
| 严格保真闭环 | 新来源、自由生成、实际prefix复用与完整服务成本 | 既有主18完成，0/1,296 compiled future ID差异；不同来源的独立Qwen成本变体负结果完整保留。不把闭环倍率叫开放到达SLO容量 |
| 本轮保真固定到达桥梁 | 同一协议中任务质量、真实复用、排队、SLO Goodput和完整wall能否同时成立 | Raw-only标定7/7已验收；正式390ea831已生成，24正式单元尚未产生，不提前填正收益 |
| 独立隔离Gate ON/OFF | 原经济门禁到底筛掉多少认证，如何影响覆盖、wall和尾延迟 | 6正式单元尚未运行；CPU接线只证明经济分支可独立开关，不证明性能效果 |

最终两行完成后，本文件补入实际来源级费用和Goodput入口；不依靠不同协议的高值拼成统一速度或安全保证。

## 可复核入口

- 行为/Manifest完成报告：`docs/tsc_revision_mechanism_manifest_results_20261018_zh.md`；raw archive SHA `39b2ad426f101602bed6706d1d5866665355cde3c8f3b84915c90eca1a7a3c1f`。
- 原TableIII报告：`docs/tsc_TableIII_fullcost_replay_completed_20261018_zh.md`；archive SHA `9d324d82cbb0262240cc27cab0505f694e9e37b468a2cad3b34a89774162b7cf`。
- 256补充：`docs/tsc_revision_budget256_results_20261018_zh.md`；archive SHA `892650450856f621ffa5f0dbbd583e0a1e4ab162cdc82f52851b1fa3a491198e`。
- 真实Repo：`docs/tsc_revision_real_repobench_mechanism_results_20261018_zh.md`；archive SHA `ad1916813dfdebb510d641dcb77edce4e6fbafda5daff3b8716c0df7e466cfdf`。
- CPU布局/驻留/tail/margin及PSTP索引：`results/tsc_final_existing_evidence_CPU_20261018/`。
- 完整信任矩阵：`docs/ContractKV_Trust_Model_and_Enforcement_Boundary_Matrix.md`。
- 服务新协议：`docs/tsc_revision_final_serving_calibration_design_20261018_zh.md`、`results/tsc_task_faithful_open_arrival_20261018/`。
