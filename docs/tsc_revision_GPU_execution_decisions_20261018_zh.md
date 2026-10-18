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
