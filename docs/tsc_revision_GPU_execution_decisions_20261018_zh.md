# ContractKV 三批补强：执行与决策记录

## 当前目标

完成原 Table III 同协议全成本、跨模型多语义认证必要性、合成 Manifest 实际发布/命中三批实验。先保留所有结果并完成 Markdown 总报告，再修改正文和 Response Letter。目标不扩展为新算法研究。

## 已作决策

| 时间（UTC） | 证据与决策 | 边界 |
| --- | --- | --- |
| 2026-10-18 08:51 | 两张指定 UUID 的 3090 均空闲，按已发布 v3 回执启动 formal_attempt3；supervisor=141324、worker=141325。 | 不抢占其他任务。v3 只修短 IPC 路径；模型、样本、renderer、候选、阈值、scope、评分和策略 slack 不变。 |
| 09:04:49 | Llama 第一次 Raw/Contract 配对完成，450 个未来配对。两路 service wall 为 553.6395 / 548.5580 秒；完整 wall 倍率 1.009263。Contract 的 50 个 controller 合计 134679.15 ms，实际 30 次 raw-reference 函数调用、36 次 verification 函数调用，0 次包装调用异常。 | 仅一次、一个模型的中间结果，不是四配置总结果。另 20 个预冻结 L0 会话也有实际 controller/warmup 费用，不能把“无认证 RPC”解释为零费用。 |
| 首对完成后 | 模型启动至整对结束约 13.6 分钟。总预算继续按 8–12 GPU 卡时、约 5–8 小时给总报告预留，14B TP2 与基础设施异常仍可能改变进度。 | 卡时是各 GPU 占用时间之和；不等同于自然时间或论文中的 client wall。ETA 不是新的实验结果。 |
| 第二、三批首次 GPU 前 | 将后续规模收为 3 模型 × 3 fresh-process，共 9 cells。每 cell 20 个行为候选，每候选四次真实业务；Manifest 另 15 次业务、至多两次认证。总计 855 次业务、最多 198 次 GPU 验证。 | 尚无本批 GPU 结果。受控语义挑战不冒充真实 benchmark；不把未经认证的候选称作原 frozen-safe D1。 |
| 第二、三批首次 GPU 前 | 使用实际 CALC 的合法布局、原 strict pointwise margin 和真实 raw witness。诊断中明确关闭经济筛选，以便测准入本身；候选精确绑定 observation，raw/unchecked/qualified 各自隔离 namespace。 | 不改变生产 family 资格、收益门禁、PSTP 或服务调度；不声称自动在两套证书体系间切换。 |
| 第二、三批首次 GPU 前 | 只接线现有注册 helper 与实际可信客户端的 HMAC binding 函数，随后执行真实后端请求和 PSTP；使用原有只读 residency hook 核对提交、盐、块链与命中。 | 这是受控客户端适配器，不是公共注册/IAM 网关。同步 trace 的运行成本只作诊断，不用于加速结论。可信运营者误声明可能实际发布，这个结果不能删。 |

第二、三批的源代码、案例和规则已发布至 `258f96e1af72f687463507906933cb740e00f8dc`。冻结文件 SHA 为 `6fa806899ff76baf20a5441e932ede26311b609e54c5ef5ee110d601a8a2b4e8`。远程 48 份部署文件已校验；仍需在第一批完成后做独立 runtime/tokenizer 预检，发布真实 preflight receipt 才能执行。

随后在任何诊断 GPU 请求之前，源码接线审计发现 v1 给 Manifest raw fallback 附加了原客户端没有的私有 salt。这个差异可能遮蔽原生 APC 命中，因此不采用它提供隔离证据。v2 保留原客户端 Manifest raw 的 `cache_salt=None`，单独记录默认原生 APC 与认证 namespace 的命中。原 v1 文件不变、无 GPU 执行；只在行为必要性诊断中继续使用私有控制 namespace。当前入口改为 `scripts/tsc_revision_mechanism_worker_v2.py`、`preflight_v2`，冻结 SHA 为 `9366e45e7a1d103fa2c8972a4f100d6276de5e58c5a446befa13efe2725c1418`。案例、规模、评分、margin 和原有发布规则均未改变；若跨域 raw fallback 命中无 salt 的原生 APC，必须如实报告，不能叫作整台引擎的域隔离成功。

最终接线检查还要求 Manifest 的后续 compiled 路由执行已经声明的精确 observation ScopeValid，不能仅凭 HMAC/稳定前缀匹配就覆盖新私有值。scope key 改为仅绑定实际输入和输出预算；CPU 实际函数检查确认评分答案、风险标签不影响 scope，而输入变化会使 scope 不同。当前最终执行入口是 **worker_v3 / preflight_v3 / freeze_v3.json**，SHA `7170c9101903326c582bc32e93ca2e4d7998b42b8fc5a8bb62c7d158ed8dd4ff`。v1/v2 均为 GPU 首次运行前保留的准备版本。病例、margin、评分与数量不变；分析 v3 区分接口响应不确定、明确拒绝和真实后端提交，并记录原生 APC 命中是否覆盖合成私有标记。后台完成/空闲检查后才冻结诊断 cell 的 trace hashes。这些是新诊断接线的预执行修正，不影响原 Table III worker 或历史 GPU 数据。

## 已向用户汇报的阶段

Llama 三重复在 09:27:56 UTC 全部完成，共 1,350 future pairs、150 个完整 controller。完整 wall 倍率为 1.009263 / 1.015763 / 1.009627，平均 1.011551；业务新 prefill 从每次 1,067,553 降至 736,897 tokens，降低 30.9733%。108 次实际验证调用中有 33 次未通过，全部计时保留。GPU 已进入 Qwen3-8B。该阶段已向用户汇报，后续仅在 Qwen 三重复或新的批次里程碑再报，不重复这一阶段。

用户随后询问“旧协议/新协议”和 slack。已明确：本次叫**原 Table III 同样本完整成本复测**，固定原策略参数，但完整 wall 不减任何 2s/6s slack；不能称为将策略参数全部设置 0 后重选布局的结果。另一个已经完成的**保真输入十租户主验证**是不同实验设置，真正不抵扣任何 slack，三模型全 wall 1.619036 / 1.109074 / 1.070280，已从三重复原始 summary 重新计算。两组不能混作同条件升级曲线；当前 1.2% 仅是原 Table III 条件下较小的收益，不替代保真主验证。

## 计账与解释规则

原 Table III 并列报告两项：实际完整 client/service wall，以及完整 controller 按全部 future requests 摊销的零 slack TTFT 费用。后者是组件计账，不冒充实测 readiness 分布。原策略使用的 slack 值保留，费用分析不减去任何 slack。

每次 `generate_raw`、`compact_verify` 的返回、失败和异常都保留耗时；每个 canary 有完整 controller。`compact_verify` 包含准备与传输，不叫作纯 GPU 核心耗时。原来只保存最终/成功档位的字段继续保留作历史对照，不填补丢失的旧时间戳。

行为结果同时报告 Raw 自身重复变化、未经认证候选的正/负分数变化、认证决定及认证后真实业务输出。Raw/compiled 得分相同与输出 IDs 相同分别统计；输出不同但得分提高仍不当作严格行为保持。

原 Table III 历史客户端没有完整保存全部 Prompt/Output IDs 的能力，不能从文本相同推导 IDs 相同。第二、三批使用现有 strict streaming transport 保存实际完整 IDs，不篡改第一批客户端来混合两种协议。

## 下一步

第一批 worker 按冻结队列继续四配置、三重复。并行仅做本地分析代码和小型证据整理，不在正式 GPU 时段运行其他模型任务或复制大型 runtime。结束后，第二、三批先做 preflight、取回元数据并发布回执，然后接续。最终统一汇总全部实测与失败。

## 10:52 UTC 后的无重复接续

用户最新五批目标保存在 `docs/tsc_revision_final_strengthening_objective_20261018.md`。它扩展最终验收边界，前三批完成并归档后还须按冻结条件完成任务保真 Open-arrival 与 CPU 优先的机制/尾部分析；不在前三批后提前结束整个目标。没有重建已冻结的案例或重新启动已有 worker。

- 10:52 实际 state 与 `/proc/141325/cmdline`：原 Table III 完成18/24 cells、4,050/4,725未来配对，当前 `qwen14_r1`。Llama、Qwen8B、Mistral各三重复已完成。14B TP2依序占用两张指定卡。
- Mistral完整wall三重复为0.997262933 / 0.998929610 / 0.985267121，平均0.993819888。每次50个完整controller、42次verification函数尝试、8次generate_raw异常；首个重复逐案核查为 `VerificationIncomplete: raw finish_reason=length`，不是服务器崩溃或认证RPC失败。预算128不改，不因负收益重跑。三个重复的实际耗时与异常计数保存在 `stage_mistral_three_repeats_v1.json`。其余重复的详细原因仍须在最终逐案复算时核对。
- Qwen8B三重复阶段账本另存 `stage_qwen_three_repeats_v1.json`，包括第三次较弱的1.004127499，不作替换。所有新stage文件只从已完成配对和实际日志提取，不触发模型请求。
- 后两批四个缺失项目依赖已按原字节补齐并在Linux导入通过，执行补充清单已公开于a348229；不再重复补包或改写worker。后续使用 `tsc_revision_mechanism_checked_entry_v1.py`，详见独立addendum。

### 完整成本分析定义的最后核对

对照 `tsc_revision_tableIII_matched_cost_audit.py` 及已复现的历史统计发现，分析准备版v2的residual诊断错误地使用了编译子集均值。原Table III的业务均值始终使用全部future；只有残余验证费用的分母在Qwen8B/Mistral取certified futures，在14B/Llama取all futures。新建 `tsc_tableIII_fullcost_analysis_v3.py` 明确按原定义报告A；B为全controller零隐藏费用摊销，C为直接完整wall。v1/v2源文件保留，尚未生成任何最终分析结果；这次仅修正分析代码，实验、样本和计时不变，没有重新运行GPU。v3另外保留实际服务端生成tokens总量/分桶和业务prefill、尾部，不能由这些总量伪造逐请求输出长度。

### 等待GPU期间的既有证据复用

新CPU分析 `tsc_revision_final_existing_evidence_CPU_v1.py` 对既有保真主验证4,860个future做时间恒等式与真实日志核对，提取逐进程p99以上54个请求；全部为L0路由，其前一wave注册等待可由实际日志定位。该等待由同wave租户共同经历，不能按租户数倍增为GPU费用。51个实际认证响应的完整margin只作固定阈值网格的后验谓词分析，不重新评估未执行候选或推断未来安全。

PSTP复用Phase16R、Phase17并发故障与Phase18生命周期的原始CSV/JSON，保留harness decision与自动接线、源级故障与普遍并发证明之间的边界。已有故障证据足以支撑第五批对应检查，暂不重复GPU压力测试。新Open-arrival结果和真正Gate ON/OFF的差额仍待后续独立协议处理；这些CPU结果不冒充GPU补测完成。

## 11:27–11:39 UTC：继续原worker及补齐CPU可观察性

上一目标轮分类为progress：实际接续五个未执行单元、保存十九个完成单元，并生成真实日志CPU分析与公开源文件。当前轮重新读取完整五批目标，核对Git main与远程SHA，并在`/proc/208398/cmdline`确认接续worker仍运行，不重复启动。11:39时为21个完成单元；14B r2 Raw已持续写入真实请求记录，GPU两卡100%利用，无新worker错误。

CPU新增两项完成记录，不启动模型：

1. `native_tail_v1`核对18cell/10,800次实际业务，补齐4,860个future的真实scheduler等待、running/waiting、pool free/used/total与块表。初次快照不是全程峰值，known-hash重分配不是完整eviction计数。性能矩阵使用已有native初始metrics和Prometheus，不安装原文件已注明“timing unsuitable”的重型residency hook。
2. `margin_two_floor_v2`在同一已声明网格中分别改变raw和candidate/EOS两阈值。六个R3原始文件与归档SHA匹配，三个doc99重复均确认candidate margin 0.40625及一个Raw输入token变化；0.25 candidate floor仍不能排除这三个旧见证。该结果关闭“仅靠margin即可支持变化输入”的误解释，不用于选择新阈值。

第一批输出可观察性继续严格区分：原驱动保留完整输出文本，可报告真实字符/UTF8字节长度；未保留的逐请求模型token长度、未来finish reason及IDs不以重分词补造。新增`tsc_tableIII_output_observability_v1.py`仅在24单元完成后做这项审核，同时从server access log独立数实际认证HTTP调用。Llama首个完成cell已确认36个函数尝试对应36次实际HTTP请求，不能把530条initial metrics当作GPU forward计数；legacy复用request ID、初次观测与实际RPC是不同分母。完整耗时仍按每次函数调用和controller的真实计时保留。

## 12:05–12:24 UTC：第一批关闭，后两批接续

原TableIII24单元在12:05全部完成。完整wall均值：Llama1.011551、Qwen8B1.020224、Mistral0.993820、Qwen14B TP2 1.109442；不抵扣slack。A/B/C和全部质量变化分别入报告。453次真实HTTP认证、155次非通过尝试、30次异常与60个无包装RPC的L0 warmup均有计时。801成员双端校验通过；本地12/525/4725行全字段复算一致。

负结果保留：旧模式Qwen RepoBench389/r3/turn1的次级分数0.72到0.38在compiled路由；另两下降在Raw回退。原sanity proxy未标出前者；Llama的三个proxy下降在QA F1两路均0的同一来源。评分分列、协议分列。三重复文本检查不能唯一归因，不将其一律称模型噪声，也不据它调整新正式参数。

后两批一次CPU预检完成，实际回执2262851f在0f1ef20公开后，12:22启动原v3 worker，supervisor236905/worker236906。见GPU_LAUNCH_STATUS_20261018.md。共用9cells而非18；第一wave状态文字未及时更新，但实际execute PID及两卡EngineCore已核实，不重复启动。没有重做全权重SHA、原9/19 CPU或冻结病例。

## 12:30–12:38 UTC：诊断固定端口复用修复

第一wave两个cell完整完成，190次业务生成。第二wave在模型/客户端启动前因固定8990/8991端口bind失败退出；Llama r1和Qwen r2的旧attempt1仅为空目录。没有GPU输出被丢弃。该wave复用端口问题在启动前审查中漏检，现已单列基础设施修复。

新continuation_v4复用两个完成cell的18个文件，只执行剩余7个，端口9202至9208。原run_cell仅一个端口赋值AST表达式变化，其他AST相同，原55文件、collector/backend、病例、模型、margin/scope/评分与原runtime预检均不变。原model/runtime回执2262851f直接复用，没有重做全SHA、runtime副本或tokenizer/窗口预检。

repair SHA8d3bd864与CPU端口/AST回执0ee814b5在Git d4914ec公开后，12:37实际启动supervisor243420/worker243421；12:38其真实命令、RUNNING状态与两卡EngineCore已核对。旧236905/236906已退出，禁止重新执行旧全9cells。以PORT_CONTINUATION_v4_zh.md及实际新PID为恢复依据。

## 后续实现的只读接线提醒

保真adapter_v2的RENDER_BINDINGS覆盖原live、R1R、R4闭环及candidate_plan，但不覆盖r4_live_fixed模块本地导入的_ordered_text。新增保真固定到达wrapper在正式冻结前必须显式把该本地引用绑定到同一保真renderer，并用预检实际Prompt IDs验证Raw和compiled均一致。否则Raw保真而compiled未来又插回历史chunk heading。此处目前仅做源码审计，没有修改既有协议、产生新数据或调节scope。

新增服务桥梁的到达/SLO标定必须来自新保真Raw-only数据；旧R4固定到达5/54继续原样保留，不重复、不当作新服务桥梁。不同协议的结果不能合并。公开实验报告/全目标完成边界仍按五批目标，当前只完成第一批，第二/三批实际运行中。

12:43核查剩余worker实际仍运行：Llama r1已产生真实chat/verify请求，Qwen r2在加载与编译。Qwen该次weights load实际272.45秒（model loading 272.83秒），随后torch.compile约57.52秒。该日志说明“暂时无responses”不能作为worker停止证据。保持现有队列，不为了缩短启动时间中断健康进程或改变已冻结cache/顺序；新协议的GPU时间估计需单列这种模型启动占用，不将它混入论文service wall。以后新冻结编排预先采用每cell唯一端口，避免再复用短期关闭的监听端口。
