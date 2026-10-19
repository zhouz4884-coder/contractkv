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

## 12:44–12:57 UTC：修复真实raw截断的异常处理

Llama r1第16个候选的raw参考达到原64-token上限。原splitter正确抛VerificationIncomplete，但SingleShotRegistrar只catch ValueError；前者继承RuntimeError，异常逃逸后客户端退出。原Raw输出/分数0、63条业务、15个完整案例、13次实际RPC均保留。Qwen r2完整完成，三个完整cell保持不动。

窄修复只把该已有EOS/answer不完整条件显式返回INCOMPLETE、0RPC/0commit/L0 fallback，不延预算、不降低floor、不改scope/评分，不捕获其他RuntimeError。用实际失败见证做本地/Linux CPU回归，原方法抛异常、修复后无RPC；另15个已完成引用的非计时决策、payload及record事件全部一致。CPU响应使用已记录stub，不冒充新GPU验证。

原55文件与backend/runtime继续不变；客户端wrapper在独立进程给原方法安装窄catch，再运行原collector。新的run_cell只有port和client wrapper命令两个AST表达式不同。失败实验单位是95业务fresh-server cell，不能接半个cell；仅未完成的Llama r1完整重测，其他五个未启动cell首次运行，前三个完整不重测。正式9cells/855业务，额外63条失败记录必须另列，实际观察总量将为918（若无后续失败）。

v5 repair 0b8a75cd、CPU接线回执8732bf66在e966c20公开后，12:56启动supervisor251069/worker251070。12:57实际/proc命令及RUNNING已核实，原model/runtime回执2262851f复用。旧243421已退出，不能再dispatch v3/v4。详情INCOMPLETE_REFERENCE_FIX_v5_zh.md。该fail-closed修复也应进入后续新冻结服务客户端；正常资格算法不变。

## 13:01 UTC 后：等预算补充条件，保留当前执行

最新用户询问能否提高 token 上限，使 Raw 和 ContractKV 尽可能正常结束。实际读到 Llama 和 Mistral 的同一受控算术病例在 64 tokens 时尚未给出最后数值；不是已经观测到无限重复。决定新增单独 256-token 条件，全部 20 个原病例、三个模型各一次进程，共 240 次生成、最多 60 次资格 RPC。四条生成路径同预算、同评分、同 Prompt/布局、同 margin/EOS/PSTP；不重复 Manifest，原 64-token 矩阵保持运行。更长解释即使包含正确数值，也可能违反原整数-only 契约，不能事后更换主评分。

协议位于 `results/tsc_mechanism_budget256_20261018/protocol_v1.json`，SHA58db2c3c；执行冻结007e4bef。120 个原 Prompt 形状复用预检，最大 Prompt+256+EOS 为1,023，全部适配16K。没有重做模型/Tokenizer/runtime准备。原 collector 的 setup/generate/qualify/完整20病例循环 AST 保持一致，仅跳过后续 Manifest 部分，终端计数80；worker仅显式替换端口/source/policy hash/client及两项Manifest计数，其余AST一致。CPU接线使用明确 fake transport/registrar，80次同预算调用与20病例全覆盖通过，不冒充 GPU 效果。

只有原9单元完成并归档、Linux零GPU检查回执及源码公开后，才启动补充条件。不按输出选择有利病例、不自动加码512、不覆盖64结果。此为观察截断后的预算敏感性诊断，不能称独立盲测，也不提供服务吞吐结论。

### 预算执行入口的零 GPU 兼容修正

256补充v1在Linux检查AST SHA时停止，新增GPU请求0。Windows Python3.13的空type_params字段使dump与Linux3.10不同；结构相同断言仍通过。保留v1源和失败回执，v2改用仅忽略空type_params的规范JSON，原字节SHA不变。Linux v2实际回执afb4e668已与源码公开，当前入口budget256_worker_v2，freeze0d4c2ec5；v1不能启动。分析代码在cb36f84先行公开，64描述性基线取每模型第一原冻结重复，256全病例各一次，不混合分母。

## 后续新源与服务桥梁的预执行边界

新的已知来源排除索引没有打开候选池，只读历史来源身份。原567来源，加保真主验证6、成本适配独立6，以及TableI独立125，实际并集为704；开发四来源已在567内。不能沿用过时的579来源数而遗漏TableI。索引和每个输入SHA保存在final_known_source_exclusions_v1.json。

源选择协议已写入新目录，但尚未选新源或产生GPU结果：先从704排除集按固定hash选真实Repo诊断3源，再将它们加入排除集，选桥梁HotpotQA/RepoBench各3。独立seed2026101803/04；只以关键字段存在和共同16K容量筛选，不读答案位置或模型结果。代码有父9cells完成且归档的硬门槛，禁止提前打开新候选池。原保真packer、renderer、生成预算128/384与catalog均按SHA继承，tokenizer只重核已有资产身份，不复制或重新下载模型。

服务桥梁正式工作量预定为6个模板、每模板6个注册租户、每租户10轮，即360业务/单元，最多24个正式单元=8,640业务。此前目标没有冻结租户/请求数。此选择是在新来源输出前为控制完成时间作出的，保留原10轮query目录与原declared_reuses(turn,tenants,2)函数，不能改写成旧10租户同协议对照。36个注册身份与GPU实际最多2请求分别报告。正式到达/负载/SLO仍须来自Raw-only标定并在任何正式Contract输出前再冻结。

固定到达新wrapper显式绑定原fixed模块本地_ordered_text，其他执行循环不变。CPU用已有SeeAct真实CODE_PREFIX检查：旧本地引用仍插入分片标题，完整7,371字符前缀不能连续出现；显式保真绑定后连续保留，且与candidate planner的renderer是同一函数。测试后引用恢复，不修改历史fixed运行或已有结果。该CPU修正尚不是GPU性能结果。

另有有界Gate OFF控制接线，只覆盖成本模块decide的经济拒绝分支，保留原粗/细成本计算与原始决定作审计，reference scope、语法、margin、EOS、PSTP均继续走原调用链。无效数值特征仍拒绝、继承家族L0仍不能越权。CPU实际特征检查通过；正式Gate OFF数据尚未运行，不从此推断排队改善。

21:12香港时间的ETA根据已完成保真18cell实际服务wall估计：每600业务的Raw单元约33–45分钟，另有模型加载/编译。核心当前6/9，预计30–60分钟内交付三批阶段结果；整个五批含新服务验证、必要补充及归档估计10–16小时，前提两卡持续独占且无新故障。这是计划区间，不是已完成结果或确定承诺。

## 14:20–14:26 UTC：阶段进展与后续服务编排

原三批，以及256-token和真实Repo补测均已完成归档和独立复算，不重复运行。详细现状单列在`tsc_revision_stage_progress_20261018_zh.md`。TableIII完整wall Mistral负收益、旧compiled次级掉分、Manifest可信误标和原生Raw跨域hit、真实Repo M/L语法早拒与Llama384截断全部保留，不为了正面叙述改分母。

唯一GPU工作是Raw-only baseline supervisor285458/worker285459。14:25后前两个Qwen cell各120业务完成，state实际已记2个完成；随后同worker开始M/L。没有重复准备564文件快照、模型全SHA、runtime或已完成实验。

新写Raw推导与正式矩阵编排，先按冻结公式推导common=.9min(Cq,Cm,Cl)、Qhigh=1.05Cq及SLO，不能查看Contract结果后改点。正式24和Gate6代码目前只做CPU控制：轨迹/原loader绑定、配对同卡同到达、r2交换GPU/次序、双ready与全wave失败保留。Windows和Linux相同五项CPU检查通过，fake transport不作GPU效果。新代码单独部署5个小文件，原客户端/564快照/runtime不改。正式实际轨迹与freeze仍等待Raw标定结束；编排通过不等于正式服务已执行。

服务数据的主要Goodput在全部warm+future中同时满足readiness TTFT和平均TPOT，分母为含计划idle、失败认证与最终drain的实际完整wall。原双请求wave barrier保持并显式报告，不冒称任意高并发开放队列。原生initial new-prefill只证明逻辑未缓存输入工作，不能当GPU毫秒或包含全部preemption重算的总量。主矩阵并行endpoint与隔离Gate协议分开，不混借Raw基线。

## 14:26–14:36 UTC：预执行统计入口、硬检查与原文排重

当前Raw-only仍为原worker285459；14:36 Mistral94/120、Llama106/120，Qwen两个已完成。没有新派发或停止测量。正式服务代码尚未产生任何GPU结果；CPU接线的第六项新增硬检查确认，360个fake配对中一个compiled ID变化会阻止后续模型扩展。该同样检查在跨模型完成后、Gate消融之前也执行。发现有效资格内反例时先归因，不能为继续矩阵而放宽条件。

新增独立分析入口只读取原始证据和冻结scorer：复算全部业务任务分数、实际IDs/finish、scope生命周期、RPC与server access log、native块/命中及全时钟；来源簇与进程重复分开，零基线Goodput比值为undefined，不加伪计数，也不删除该cell。另用fake CPU控制验证空compiled分层、首次分歧、零分母及来源bootstrap。RepoBench冻结主指标为本仓库SequenceMatcher相似度，不冒称程序正确或独立官方Levenshtein复现。

尾归因使用实际恒等式ready TTFT=排队+controller-to-submit+backend TTFT。固定到达时，前一wave注册可能发生在本请求到达前；因此只用实际interwave区间与post-registration时长给出队列重叠上下界，不虚构精确注册起止，也不把全部注册耗时归到每个等待租户。累计controller/RPC与并行关键路径不直接相加。

预执行代码更新仅增加上述硬检查、分析/归档入口和先发布后执行的supervisor。远端先保存旧小源postimage于preformal_infrastructure_versions_v1，再更新正式尚未使用的小文件，记录preformal_source_update_v1.json。旧Raw worker、564文件快照、实际方法/候选/预算/准入不改；这不是GPU协议结果重跑。

新增只读原文级排重：对冻结候选池中已知704个来源组对应718条记录建立完整上下文字节hash，覆盖704/704。本轮另3Repo与桥梁6源的9份完整原文彼此不同、没有任何精确已知context匹配。忽略问题和system，仅按RAG/Repo上下文与CODE_PREFIX原文；不读答案或输出，不改来源。首次CPU草稿遗漏SYNTHETIC_CONTEXT/REPO_CONTEXT类型，在结果写出前assert停止，零GPU；保留失败回执并按实际pool schema修正，v2完整覆盖。此结论不等于语义去重或所有代码片段统计独立。

## 14:40 UTC 后：Raw baseline关闭与实际工作点

4/4 baseline、480业务完成，原supervisor285458/worker285459实际退出0，GPU compute列表为空。Linux新六项formal CPU检查在测量结束后执行，回执formal_Linux_CPU_controls_v2与Windowsv3源SHA匹配。没有把CPU负载混入正在运行的服务测量。

按原公式实际导出Cq=.313519676、Cm=.198783460、Cl=.212263461 req/s，共同到达率.178905114、Qhigh .329195660。Raw推导TTFT SLO11700ms、平均TPOT435ms。SLO较宽是本硬件长输入Raw的P95结果，不为了追goodput改成更有利阈值，不将它与旧500ms点合并。高TPOT与短输出first-to-last窗口/peer prefill重叠的线索保留；没有逐token/kernel轨迹，不唯一归因，不临时换调度算法。

独立下载4份Raw原文共30,174,361 bytes，各SHA匹配。从原文重算容量/P95/SLO/正式负载精确一致。首次Windows派生文件因CRLF、其后因Python3.13/3.10浮点sum/libm的约1e-13秒offset差异未逐字节相同，两个失败CPU视图保留。最终以明确1ns容差核全部arrival offset，实际最大3.410605131648481e-13秒；成员/seed/顺序/端点相同，其他推导字段精确相同。实际执行仍只读取原Linux arrival SHA，绝不将本地重生成trace换进去。独立回执不能写成全部字节一致。

14:44:38 UTC，实际derived计划SHA9d1a3efe及3个trace在Git669898c公开并核远程后，启动Raw profiles supervisor301481/worker301486。14:46 /proc实际命令、RUNNING状态和两个EngineCore PID302375/302442均已核验，模型正在准备，不重复派发。原4baseline不再运行。新server端口9604–9606与原baseline不冲突，source_snapshot/runtime不复制。正式Contract仍未开始。

独立分析现明确标记qwen/cross/gate执行regime及peer条件，避免把隔离Gate与并行主矩阵混比；五项CPU数学检查v3通过。归档入口亦纳入原小源postimage目录中的带SHA后缀文件，防止只按.py后缀筛选遗漏预执行版本。两个本地失败推导视图的4个派生JSON/trace文件分别保留，不能只留“失败”标签。以上均未改变Raw/GPU客户端或冻结门槛。

## 后续CPU证据交付与一次文字归因更正

R3.1新增实际顺序提取：直接核三份TableI原始gzip的completion SHA，读全部3,750实际messages/character_spans，交付五家族初轮/未来轮和2–18条真实历史消息的位置。旧R4另500 CPU渲染、新桥梁另60 CPU渲染，已导入源均匹配各自freeze，区别于实际GPU数量。受控TOOL_OBS包装不包含增长history，不混成同一协议；旧代码50/100 Repo渲染CODE_PREFIX为空，当前30/30完整包含。Azure固定版本两源码及MIT许可/SHA重新核对，只支持条件性布局例子，不支持生产频率或旧TableI数字。

36项审稿矩阵及按协议分开的性能/尾报告已形成，服务新30单元仍标进行中。逐请求复核纠正了一处我从前摘要沿用的归因推断：54尾请求并非48前序PASS+6失败RPC，而是42前序PASS、6失败RPC、5未发RPC的scope拒绝、1无前序注册。5个scope检查约4–9ms，不能解释全部尾部。原CSV/计时不改，回执faithful_p99_outcomes_recheck_v1保留。该检查的AssertionError曾被PowerShell后续命令掩盖为整体exit0，草稿进入5bebe0c历史；后续立即更正，不改写历史。以后关键检查与发布步骤按真实返回码顺序执行，不以最后一条Git成功替代检查成功。

## 15:14 UTC：全部Raw标定验收与正式协议冻结

原profiles301481/301486实际退出0，7/7 Raw、840业务、756future验收通过。独立分析重新核全部实际Prompt IDs/到达SHA/预定时刻/native/评分，0认证RPC、0compiled，不能把此零数当作认证安全结果。正式prepare核Windowsv3/Linuxv2六检查源完全相同后，一次生成6到达trace、30jobs和390ea831 freeze；58个依赖文件已取回本地逐SHA一致，尚无正式CT输出。

Raw .4/.7/1.05Cq三个点分别107/120、89/120、8/120双SLO达标。高点基线较小，不改lambda或SLO来美化，也不以由小分母放大的倍率当强结论。正式优先绝对Goodput/达标数/不确定性。

在首个正式CT结果前新增只读统计addendum：固定原390ea831与主进程配对统计，另外联合重采样3 paired进程、每家族3来源，保留来源内所有tenant/turn；仅重加权实际达标分子、对应进程wall保持已测值。主敏感性是绝对Goodput差，不称新队列或来源总体容量CI。出现任何零baseline draw则ratio区间不定义，不加伪计数/删样本。新增GPU0，不改变条件/预算/安全门槛，作为独立文件预公开，不覆盖原freeze。

本次也明确内容保真不等于原生completion包装复现：服务Repo仍用声明的instruction-following chat，CODE_PREFIX后有任务指令；实际顺序公开，不在已冻结Raw之后临时换位置或未经对照将所有M/L语法拒绝归因于它。四份指定MD现均已建立，正式30结果仍待回填，不能据文档数量宣布目标完成。

15:23:25 UTC，390ea831主freeze与统计addendum5fe5ae0b在f2c1fab预公开，并逐一核58依赖的Git blob字节/本地SHA/远程ref一致后，实际派发formal supervisor318277/qwen worker318282。15:24 /proc与两个EngineCore319110/319177已核，首wave共同/高负载Raw正在准备。主矩阵24与Gate6将按既定序列自动接续，任何未解释compiled配对变化会阻止跨阶段扩展；不重复Raw7或重新生成formal freeze。新的源/依赖/CPU回执均复用已冻结对象，没有模型/runtime副本或完整权重SHA重做。

## 16:35 UTC后：首次Qwen配对与继续冻结的决定

四个首次重复cell全部完成；只读watcher确认实际qwen PID匹配launch后结束自身（unified exec79309退出0），不影响318277/318282主流程。原模型管理器按r2反序/换GPU接续。没有重新启动任何实验。

两点各18/324编译future、22全部编译业务，精确ID/finish对Raw及实际见证均0变化。scope决定各1PASS、8无声明exact-observation复用、6候选token-margin拒绝、3语法拒绝；六个candidate minima全负（−11.313至−.406），不靠略降.125放行。经济门禁不是最终拒绝原因。业务logical new-prefill降低4.407%，另有7实际RPC及约28.4s完整controller工作；13编译full hit/9zero，资格不保证全驻留。无完整本轮驱逐时间线，不将9个都断言为已证明驱逐，也不据此改缓存算法。

common wall2008.481→2008.505s、Goodput .129948925→.128951612（261→259达标）；high wall1161.978→1179.758s、Goodput .006884815→.022886042（8→27）。小baseline不能只报3.3×。各点全路由2个掉分均L0，上升4/6保留，三Raw重复尚未完成，不先归因为噪声。

投影只读已完成4cell并核原Raw SHA，nice19，两个执行各约1.49/1.59s、GPU0请求，保存源码与原输出。后续正式主分析仍逐业务独立重算评分/费用，不能以该初览替代最终统计。当前没有已获准子集行为失败或发布不变量失效证据；弱收益来自可见的稀疏资格/成本/驻留，选择完成原三重复，不换来源、不调Scope/16词界限、不放宽margin、不追加有利负载或新GPU探针。若之后出现可复现机制缺陷再按最小修复/新冻结处理。

## 19:01 UTC：Qwen阶段12/12与跨模型接续

只读qwen phase watcher unified63561实际确认PID318282运行及progress，最终12完整/exit0；cross worker414783被原318277自动启动，6组compiled配对均0ID/finish变化。该watcher自身退出0，不再向关闭session写入。没有重启动任一模型实验。

低优先级复用既有投影入口仅读取已完成r2/r3，未增加GPU；本地qwen_stage_interim_summary_v1聚合所有3rep/两load。每load54/972 compiled future、66全业务，均只doc90一个scope；native39full/27zero，资格拒绝分解每rep1PASS/8scope/6负margin/3syntax一致。common pooled wall .999986×、Goodput .126074002→.126569282（761→764达标）；high wall .990905×、Goodput .013177818→.023277243（46→82）。三次high wall均小于1，全部保留，不能只取首次3.3×的小baseline比例。

全route common13up/5down、high14up/6down均L0；同位置三个Raw控制分别出现3/5与4/6个下降变体，不能据此对另外4个或全部事件作唯一因果结论。Raw两两比较分别16/22个ID/finish变化，比较共享三个控制非新请求，不当独立样本。

本组没有声明有效的compiled子集行为反例。当前合理决定是继续原M/L与Gate有界计划，而不是因Qwen低覆盖停止/换源/改scope/改Ladder。旧DEV L3选择在完整长输入上可能较激进，以及prefix/Raw工作集竞争的解释都作为未验证假说记入阶段报告，不用heldout结果为这些假说调参或追加GPU。完整30与所有源/进程敏感性、独立评分/归档仍待完成，Qwen阶段不能替代全目标。


## 23:05 UTC：主服务24完成与隔离Gate接续

实际cross414783完成12、exit0，6组compiled ID/finish全部0差异；原318277自动启动gate517543，23:07 /proc实际命令及RUNNING已核。cross watcher unified86765退出0，不再向关闭watcher写入。未重跑主24。M每重复18future/22全业务编译，L每重复16future/16全业务编译；全部12组主编译检查通过。metadata pooled wall M .999372、L .999568，不把近1计时比当SLO净收益或完整独立质量复算。

已取回12 cross小summary/completion/audit/drain及正式exit/feasibility，仅聚合现存metadata写main24_completion_metadata_v1.json，未新增GPU。完整native、SLO、评分升降、Raw控制和不确定性等Gate6结束后统一验收，不在隔离测量期运行重CPU分析，也不因结果弱改条件/加点。


## 23:17 UTC：等待Gate期间完成证据分母与最终验收清单

当前只读watcher75961确认真实Gate worker517543命令匹配launch，首单元82/360、0/6完成；原supervisor318277继续运行。没有重新派发、预检或改动冻结线上代码。最后GPU结束前不在远程跑重CPU分析。

本地将四MD里“24正式尚未产生”等旧描述统一为主服务24完成、Gate运行中、完整统计仍待验收；同时由已独立复算effects CSV直接展开三模型×五类共15行分母/实际变化/准入/升降分/RPC与资格费用。每模型加总与旧summary一致、所有错误准入/拒绝新增发布字段核验，无新增GPU。完整准入162次RPC与18个RPC前结束分开，避免把全部102个变化拒绝都误写为GPU verifier拒绝。

新增ContractKV_Final_Experimental_Completion_Audit.md逐项列目标、实际证据与未验收项，不把文件存在或零观察事件当作全目标完成。主服务wall约0.991–1.000×与低覆盖均保留，继续原六Gate、统计、独立复算和归档后收口；不按当前结果调阈值、扩大scope、换源/改负载或新增算法。正文与Response Letter仍后置。


## 23:23 UTC：一次性CPU后处理接续，等待GPU全部退出

后处理只调用既有冻结的formal analysis、预注册source sensitivity、post integrity三入口，不改统计方法、SLO、来源或任何线上代码，也不启动GPU。新编排源和计划先在cef70e3cdb0e74848b01d46c88b60afb8b285691公开并核远程SHA，才部署并启动单一CPU进程525181。计划SHA822d6c53631af7948cd73e01ae3fa35a749ed4fd35725288e86b2b43854cfffc；原390ea831及ac65994e主分析SHA仍匹配。

真实只读check返回75，确认Gate517543/master318277仍活跃；后处理以nice19等待，不运行重分析。部署后三文件逐字节匹配、实际/proc命令和WAITING_FOR_FROZEN_GPU状态已取回。要求三GPU阶段完成/exit0、所有实际worker与master退出后才开始CPU；新旧输出目录存在即拒绝覆盖，任一分析失败保留证据并停止，不自动重试。完成状态仍为待CPU证据同步、package、本地独立复算和最终报告，不能自动关闭研究目标。恢复时先查525181及postprocessing_v1/execution_state_v1.json，不另派发重复分析。

部署失败也保留：第一次Paramiko仅用x模式创建了0-byte源码，写入时报File not open for writing；未启动任何后处理或新GPU。空文件与回执移入postprocessing_infrastructure_v1，再用wx排他写入并逐字节核验。第一次Git push网络退出128，常规HTTP1.1重试成功后才核SHA/派发。原始GPU测量、冻结文件及已完成cell均未覆盖或重跑。


## 香港2026-10-19：固定到达时钟上限的事后CPU核对

第一Gate ON单元已完成360业务/324future，18 compiled future、7次RPC、wall2008.493s；原worker自动进入r1 OFF，无隔离Raw基线，不计算该单元的独立加速。只取回completion/summary/audit三小回执，未在GPU测量期跑完整分析；postprocess525181真实命令仍匹配，保持WAITING。

独立检查完成的主24 metadata及实际冻结arrival，发现完整wall解释必须考虑最后到达下界W≥A。12配对事后CPU派生出ΣRawWall/ΣLastArrival：Qcommon1.005490、Qhigh1.069952、Mcommon1.082285、Lcommon1.102157的宽松数学上限。Qcommon计划到达跨度已占Raw wall99.454%，所以固定load下wall约1不能单独反证请求工作减少，也不是GPU空闲99.454%；需要与原定Goodput/延迟/物理工作共同判断。这不是观测优化或容量CI，不据此改负载、追加有利点或更改主统计。Qhigh实测wall变慢等负结果仍保留。

脚本tsc_revision_final_arrival_wall_bound_v1.py及arrival_wall_bound_v1.json保留全部metadata/trace SHA。第一次CPU推导误以为completion包含summary.json哈希而StopIteration，尚未产出结果、0GPU；失败源与回执另保存在post_hoc_clock_analysis_failures_v1。核对真实schema后用summary.raw_file_sha256对齐completion的raw承诺，metadata自身SHA完整记录；原始完整时钟仍由冻结主分析复核。没有更改或重跑任一GPU单元。最终package前需要同步本事后脚本、结果及失败目录到远程，避免归档遗漏。


## 00:20 UTC：首个Gate ON/OFF完整配对，继续既定两重复

只读watcher75961确认Gate2/6完成、实际517543仍匹配launch，原318277已按计划进入r2 OFF先跑。首次配对720业务完整，ON/OFF均7实际RPC和18/324 compiled future，完整controller累计28.147/27.999s，wall2008.493/2008.522s。只取回完成metadata并核到达SHA、原raw承诺和计数，没有新增GPU或完整远程重分析。总数相同不足以证明所有请求准入决定相同或筛除率0；不把单次约0.029s wall差当优化结果，等待逐请求和完整三重复。

postprocessing525181的实际命令再次核对，状态仍WAITING_FOR_FROZEN_GPU且无CPU分析stage提前执行。剩四Gate按原冻结继续，不改成本公式、scope、margin、EOS、候选或到达负载，不因首次计数相同增加有利点。


## 01:20 UTC：Gate3/6与归档Root依赖完整性补查

终止了仅用于观察的functions等待cell789以便完成本地归档审计，未终止unified watcher75961或任何GPU/CPU实验进程。直接SSH重新核对实际517543及525181命令：Gate RUNNING且3/6完成（r2 OFF已结束），CPU仍WAITING_FOR_FROZEN_GPU。后续只继续同一状态，不重复派发。

静态选择审计找到现有打包入口遗漏5个已经冻结但位于Study外的Root文件：两配置、开发cost calibration、mechanism_worker_v3及tableIII_worker_v3，合计约144KB；五者真实存在并与原freeze SHA一致，测量/校准数据未丢失。打包入口本身未绑定390ea831且尚未生成归档，因此在保留旧源后补齐原58个Root依赖的选择、SHA和inventory/receipt断言，并将校准/正式分析source-freeze SHA与原文件/预公开回执相连。包不包含模型权重或runtime cache；原始模型/runtime大文件仍用先前独立归档和身份回执引用。

本地CPU检查58/58原依赖SHA通过，新的package入口SHA51ebe0f9c0e0aabfc89b336b1071e0ee7e123d40e9cb54faff38c87a62ca28a2；这只证明选择逻辑与输入身份，不是实际归档或性能结果。保留packaging_infrastructure_versions_v1全部旧源与回执。等GPU和自动CPU分析结束后，再按实际SHA保存远程旧入口postimage并部署新包入口，逐字节同步新增CPU证据后生成原包。没有改任何冻结测量/评分/统计入口，也不需要GPU重跑。


## 01:33 UTC：明确硬性证据与主动强化的区别，等待停止范围确认

补入总报告的通俗实验地图：批次是执行分组，不是审稿人编号；前三批直接对应成本、认证必要性、Manifest关注点。第四批24固定到达主单元及新Gate六单元为后加主动强化，不能说成审稿人逐字要求的规模。旧保真闭环18单元与新固定到达24单元回答的问题不同，6/10租户是设置差异，合法覆盖/驻留则是实际测量结果，不能混写为同一因果因素。

用户提出重新评估额外实验的返修必要性。已说明第四批GPU已全部结束，建议优先收口；通过唯一异步问题确认是否停止剩余Gate或完成原冻结六单元。最新只读回执4/6完成，涉及余下两个单元，已向用户更新。停止范围尚未得到明确回复，因此没有删除结果、修改冻结计划或擅自终止既有GPU任务；没有人工新启动GPU实验。若用户选择终止，应另存明确scope amendment与受控停止回执，并将Gate标为部分完成，主24和原三批仍独立验收，不能伪装完整三重复。


## 停止范围待确认期间：仅准备原始包的本地独立验证入口

复用既有归档校验的字节/成员核对模式，补充适配新JSON inventory/parts receipt的离线入口tsc_revision_final_local_archive_v1.py。它只验证分片/拼接SHA、成员集合/字节/恢复文件及全部原冻结Root依赖，拒绝越界路径、链接和覆盖旧尝试；不启动GPU、不改数据、不进行科学评分。无论最终选择完整矩阵或按用户新指令提前收口，已完成证据仍需要这一步独立交付。

当前只完成语法检查，没有可供其验收的新最终原包，也未生成PASS回执或宣称归档完成。真实原包必须在对应GPU/分析完成、实际打包后再校验并另做科学独立复算。停止范围的异步问题仍未收到明确回复，未因此人工重启、取消或追加GPU作业。


## 02:43 UTC：冻结GPU全部自然结束，后续仅CPU交付

原有编排在未收到明确停止范围回复期间完整结束：主24与Gate6全部completion，Gate/master exit均0，最新nvidia-smi compute清单为空；没有人工启动额外GPU单元。此前关于停止余下Gate的选项已无对应未执行单元，不再要求用户选择。后续只进行已有数据的CPU分析、证据归档、独立复算与四MD汇总，不新增GPU实验。

一次性postprocessing525181已完成全部三步：formal analysis约49.71s、预注册source sensitivity约0.99s、post integrity约11.61s，均退出0。远程主分析完整30cells/10800业务，90次RPC，318个compiled future对其实际见证0 ID/finish变化；其中主服务210与Gate108的比较基准不同，不合并冒称318个独立Raw配对。7+30共37单元/11640业务的后验源码、运行时、模型stat及22测量wave检查通过。新的原始包与本地独立科学复算仍未完成，不能仅据远程分析和哈希宣布全目标交付。

当前同步只涉及小CPU证据、新未绑定的交付脚本/事后解释及最新决策文档。原58个冻结Root输入逐项保护，不覆盖任何不同字节的冻结文件；旧未绑定入口/可变文档若更新，先保存原字节postimage。完整原包将含补齐的58依赖，新源码/历史均保留，不复制模型或重建runtime。
