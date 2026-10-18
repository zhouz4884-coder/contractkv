# ContractKV TSC大修：最终补强实验总报告

**执行状态：进行中。** 原三批、256-token、真实Repo与Raw7/7已完成。23:05 UTC主服务24/24 GPU完成并通过编译ID/finish检查；隔离Gate6正在运行，统一统计、独立复算与最终归档尚未完成。这不是整个五批目标完成声明，也不是正式Response Letter。

## 1. 总目标与当前判断

本轮保留CALC、Scoped Behavioral Certification、PSTP、Service-Template Certificate四项原有机制，检验同一个命题：**结构上重复的内容，只有在布局、行为资格、身份与事务可见性共同受控时，才成为可复用的共享KV服务状态。**

已经取得的实证进展是具体的：

- 原TableIII全费用缺口由同cohort新计时闭合，失败/异常/多级下降不再缺账。
- 依赖合法候选确会改变自由生成；180个受控候选中102个实际变化全部被拒，78个不变候选获准并在后续请求保持。
- 真实Repo代码任务中，Qwen两个来源获得9,712/3,328-token前缀的实际复用；这不是合成赋值案例或纸面token上限。
- Manifest注册→绑定→真实发布→后续命中的链条已实际运行，同时证实可信语义误标及Raw原生APC不受同等隔离的风险边界。
- TableI独立结构测量、原RULER/Goodput统计重算和五家族真实raw顺序已经可追溯，不能再依靠未恢复的旧数值链。

主服务24个单元已完成，正在核对的关键桥梁是：**在新六来源、相同固定到达和SLO、完整服务费用下，质量、合法覆盖、物理复用和Goodput能否同时得到支持。** 已完成的编译配对检查未观察到ID/finish变化，但新来源资格稀疏，完整wall没有显示加速；最终判断仍需完整评分、来源簇统计、原始归档和独立复算。

## 2. 五批工作与实际执行差额

| 批次 | 原科学问题 | 实际规模与状态 | 当前结论 |
|---|---|---|---|
| 1.原TableIII完整成本 | 原部署数字计入全部资格开销后还有多少收益？ | 24/24 fresh-server cells；12配对；4,725 future pairs；完成归档/独立复算 | 四配置直接wall并非都快；A残余slack、B完整controller摊销、C实际完整wall必须分开 |
| 2.跨模型机制必要性 | 合法重排是否仍会改变行为，认证能否阻止不支持的发布？ | 三模型×三fresh重复，180候选、720正式行为生成；与Manifest共用9cells；完成 | 102实际变化、其中30掉分全部拒绝；78获准后0变化；拒绝新增发布0 |
| 3.Manifest/绑定/发布 | 检查实际在哪执行，误标和跨域Raw会怎样？ | 135正式GPU业务、18认证RPC、27注册拒绝控制及72后续请求；完成 | 同域18完整命中；可信误标9/9发布marker；跨域/旧epochRaw各18仍命中marker。非公网IAM/保密分类器 |
| 4.保真固定到达桥梁 | 同协议质量保持能否转化为真实SLO服务收益？ | 7/7 Raw标定已验收；24/24正式cells已完成，每cell360业务；完整分析待验收 | 210个compiled future配对无ID/finish变化；各组完整wall约0.991–1.000×，不能宣布服务加速。Goodput等完整统计待统一复核 |
| 5.消融与尾归因 | 布局/作用域/驻留/门禁如何共同决定收益和尾部？ | 既有CPU布局/位移/native/tail/margin/PSTP完成；真实隔离Gate ON/OFF6cells运行中 | 资格≠驻留；同步认证有真实尾成本；门禁真实筛除与Goodput效果待六单元完成后判断 |

两项有界补充已经完成：256-token三cells/240业务；真实Repo三cells/72业务。它们不是替换原64条件或放宽主服务预算。正式核心外另保留63次失败尝试业务及其13次RPC，不把它们悄悄删掉或加进完整cell主分母。

## 3. 第一批：原TableIII全费用结果

保持原cohort、旧renderer、候选、scope、策略slack参数和评分；只增加完整计时与必要的独立基础设施。新数据不是找回July时间戳，亦不声称July运行时逐字节复现。

| 模型 | 原residual-slack TTFT降低 | 新同定义降低 | 全controller零隐藏TTFT降低 | 直接wall吞吐均值 |
|---|---:|---:|---:|---:|
| Llama3.1-8B | 29.41% | 29.47% | −0.20% | 1.011551× |
| Qwen3-8B | 37.81% | 31.50% | 10.82% | 1.020224× |
| Mistral7B | 31.72% | 31.78% | 2.00% | 0.993820× |
| Qwen3-14B TP2 | 44.69% | 42.31% | 20.93% | 1.109442× |

525完整controller、453真实认证HTTP、155非通过尝试、30包装异常和60无RPC L0 warmup均计费用。Token节省不能直接换算成GPU秒；累计并行controller/RPC工作也不能直接相加当关键路径。

不利质量结果保留：旧Qwen Repo389/r3/turn1 compiled次级相似度.72→.38，原sanity proxy没有标出。旧驱动没有完整实际Prompt/Output IDs，不能事后重分词补造或唯一归因。这个事件不与新严格保真“0/1296”合并。

详见`tsc_TableIII_fullcost_replay_completed_20261018_zh.md`。本批关闭Reviewer3要求的原同样本全费用证据缺口；不承诺零slack所有模型都加速。

## 4. 第二批：行为认证超越合法布局的价值

五类受控挑战覆盖指令顺序、RAG证据位置、tool状态、合成代码上下文及EOS/stop。两个布局都相对于给定DAG合法；刻意未编码的顺序语义用于检验行为认证，不能声称CALC自动推断缺失边。

| 模型 | 候选 | 实际ID/finish变化 | 其中掉分 | 变化候选拒绝 | 未变化候选放行 | 获准后变化 |
|---|---:|---:|---:|---:|---:|---:|
| Qwen | 60 | 24 | 18 | 24/24 | 36/36 | 0/36 |
| Mistral | 60 | 30 | 0 | 30/30 | 30/30 | 0/30 |
| Llama | 60 | 48 | 12 | 48/48 | 12/12 | 0/12 |
| 合计 | 180 | 102 | 30 | 102/102 | 78/78 | 0/78 |

180 Raw重复稳定，所有拒绝新增共享发布tokens为0。未认证候选的升分也保留：Mistral15次、Llama6次；升分不等于行为等价认证成功。Raw正分分母分别48/60、18/60、24/60，不能以相对保持证明答案绝对正确。

这是20个受控病例/模型、三进程的有限证据，不是180个独立生产来源或一般安全保证。真实Repo另列，合成代码不冒充其next-line任务。


### 按模型与挑战类型的完整分母

下表直接摘自已经独立复算的 `local_independent_effects_v5/observed_denominator_effects_v1.csv`，没有重新运行GPU。每行12个候选条件，来自4个病例各3次进程重复；“拒绝”是完整准入决定，不能全部称为GPU verifier拒绝。三模型合计162次实际认证RPC，另18个候选在RPC之前结束。

| 模型 | 类型 | 候选 | 实际变化/其中拒绝 | 不变/其中放行 | 未认证候选升分/降分 | 实际认证RPC | 完整资格均值ms | 后决策业务均值ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| llama-3.1-8b | code_context | 12 | 12/12 | 0/0 | 0/0 | 6 | 109.389 | 1157.323 |
| llama-3.1-8b | eos_boundary | 12 | 3/3 | 9/9 | 0/3 | 12 | 174.648 | 102.406 |
| llama-3.1-8b | instruction_order | 12 | 9/9 | 3/3 | 0/6 | 12 | 384.656 | 139.150 |
| llama-3.1-8b | rag_evidence_position | 12 | 12/12 | 0/0 | 0/0 | 9 | 154.693 | 910.131 |
| llama-3.1-8b | tool_state | 12 | 12/12 | 0/0 | 6/3 | 12 | 197.588 | 313.008 |
| mistral-7b | code_context | 12 | 12/12 | 0/0 | 0/0 | 3 | 79.220 | 1214.507 |
| mistral-7b | eos_boundary | 12 | 0/0 | 12/12 | 0/0 | 12 | 242.401 | 85.794 |
| mistral-7b | instruction_order | 12 | 6/6 | 6/6 | 6/0 | 12 | 449.383 | 281.539 |
| mistral-7b | rag_evidence_position | 12 | 9/9 | 3/3 | 9/0 | 12 | 249.342 | 346.035 |
| mistral-7b | tool_state | 12 | 3/3 | 9/9 | 0/0 | 12 | 263.214 | 360.533 |
| qwen3-8b | code_context | 12 | 6/6 | 6/6 | 0/3 | 12 | 262.554 | 254.385 |
| qwen3-8b | eos_boundary | 12 | 3/3 | 9/9 | 0/3 | 12 | 263.031 | 194.879 |
| qwen3-8b | instruction_order | 12 | 0/0 | 12/12 | 0/0 | 12 | 567.252 | 161.063 |
| qwen3-8b | rag_evidence_position | 12 | 6/6 | 6/6 | 0/6 | 12 | 261.038 | 236.346 |
| qwen3-8b | tool_state | 12 | 9/9 | 3/3 | 0/6 | 12 | 264.381 | 286.817 |

这15行中，观察到的变化候选错误放行、不变候选拒绝、未确定响应、拒绝新增发布token/完整块、获准后ID/finish分歧均为0；变化数为0的行不定义拒绝率，不能写成0/0=100%。`code_context`为合成赋值，真实RepoBench另列。完整资格均值含CPU及RPC前工作，不是独立GPU kernel时长；后决策业务时间含真实回退/获准路径，不能从该诊断均值推出服务加速。

### 更长预算与真实代码补充

256条件中Raw/candidate/post等预算，240回答全部natural stop，没有length。26获准后0变化，34实际变化均拒绝；原整数-only评分不因长解释最后含数字就改判正确。该检查解决了这里64-token截断的可观察性，不证明任意长输出安全。

真实Repo用三个盲选新项目，三模型各一fresh-server，L0身份控制/L3候选及Raw重复/后决策共72业务。Qwen两个来源通过，后续4请求保持ID/finish/分数且L3实际命中9712/3328 tokens；对应L0身份控制仅48-token前缀。M/L12个条件在既有语法契约早拒、0GPU认证RPC；Llama一例384-token length保留，不追加无界预算。

这里保留真实仓库内容和完整代码前缀，但使用声明的instruction-following chat适配，前缀后仍有任务指令；不声称原版RepoBench-C原生completion输入或官方Levenshtein评分的逐字复现。完整raw顺序另表交付。

详见`tsc_revision_mechanism_manifest_results_20261018_zh.md`、`tsc_revision_budget256_results_20261018_zh.md`及`tsc_revision_real_repobench_mechanism_results_20261018_zh.md`。

## 5. 第三批：Manifest与信任边界已经实测

注册helper和HMAC/Scope函数在可信内部client运行，再向真实vLLM/PSTP发送请求；不是公共鉴权网关。

| 条件 | 真实业务/控制数 | 实际结果 |
|---|---:|---|
| 显式PRIVATE共享、MUTABLE共享、非operator | 27 | 注册拒绝，0认证RPC/0对应候选新增共享提交；真实Raw回退保留 |
| 同值、同授权域 | 18 | 18 compiled，全部完整命中提交prefix，native block-hash链一致 |
| observation改变 | 18 | 全Raw；18精确scope不匹配，9另有稳定字节不匹配 |
| 跨授权域 | 18 | compiled绑定拒绝；Raw仍18原生命中覆盖人工私有marker |
| 旧epoch | 18 | compiled绑定拒绝；Raw仍18原生命中覆盖marker |

正确声明9个条件发布前缀无marker；可信operator误标9/9实际发布含marker前缀。Hash/HMAC证明身份与字节一致，不证明内容可公开；`private_suffix_excluded`来自可信声明。拒绝compiled不等于整个Raw缓存清空或引擎级跨域隐私。

原9CPU注册/19binding检查与135 GPU业务分开。没有执行外泄攻击或时序攻击，也没有时序防御。完整位置/对象/失败动作/剩余风险见`ContractKV_Trust_Model_and_Enforcement_Boundary_Matrix.md`。

## 6. 已有证据复用：结构、统计、布局与旧服务价值

- **TableI：** 独立125登记记录/114原文簇、3750业务/3375future；五家族等权稳定正文94.144%、正文native恢复0.595%，global token-pooled另列。旧85.0/2.4精确lineage仍未认证；新测量不以接近旧数字选参数。部分原文此前出现，不说125全部独立未见文档。
- **实际raw顺序：** 全3750 saved messages/spans提取五家族表，未来历史2–18消息；QA/RULER为SYS→HISTORY→CONTEXT→QUERY，Repo为SYS→HISTORY→QUERY→REPO→CODE_PREFIX。旧R4的TOOL_OBS包装另500 CPU渲染、新桥梁另60，不能与增长历史混写。Azure固定源码只支持条件性真实应用布局例子。
- **输入位移与CALC：** 既有4695 segment分析及新720布局/19440 segment的tokenizer/依赖/前缀上限审计完成，CPU结构上限不等于资格、实际hit或速度。
- **原RULER：** 30共同session、固定三模型宏均值86.67%；原CI[86.44,86.90]%复现，额外同步来源簇敏感性[86.3204,86.9911]%明确标事后，不作任意架构预测。
- **原服务工作点：** 92.9007与92.62来自不同cell/时钟；原4.81069×仅25tenant、80%load、500ms点，倍率CI[2.84751,12.60699]及绝对增量CI完整保留。80登记身份下530→149 allocator-used blocks注明2386 pool/实际并发2，不说减少72%预留VRAM。
- **认证经济性：** 原Session/Template125→5调用、未隐藏费用25.05→3.24ms/request分别证明模板摊销；同栈D1/D2 1.472/1.428req/s显示治理保留约97%性能，不用近零D0作强倍率标题。
- **驻留与tail：** 已有主18的1296 compiled future中，Qwen672 full/12 partial，Mistral300 full/42 zero，Llama135 full/135 zero。资格不保证当前驻留。54尾请求全部L0，前序42PASS/6失败RPC/5无RPC拒绝/1无注册，不能全部归因一次失败验证。
- **成本适配负结果：** 独立Qwen六源九cells，原版1.80266×、适配1.06982×，覆盖774→258/1620；全局p99点13.39→8.80s但直接区间跨零。已决定不替换默认，不在该held-out上扩成本桶或调阈值。

这些证据回答不同问题，不能把来源、窗口、协议或资格不同的倍率连成因果升级曲线。详见其完成报告和`ContractKV_Service_Performance_and_Tail_Analysis.md`。

## 7. 第四、五批：保真服务桥梁与Gate

新源按704已知来源排除集及事前hash选择：另3真实Repo机制源加入排除后，桥梁Hotpot doc90/131/187及Repo humannorm/UHGEval/spira-jira-migration-advanced。九份原文彼此不同，对已知704组718条原文记录没有精确重复；不等于语义去重。选择/packing不看答案位置、模型分数或资格结果。

4个Raw baseline实测单endpoint容量Cq=.313519676、Cm=.198783460、Cl=.212263461req/s；预注册公式确定common=.178905114、Qhigh=.329195660。SLO为TTFT11700ms、平均TPOT435ms；这是长输入3090 Raw基准，不与旧500ms点混用。3个Raw profiles全部完成，达标数107/120、89/120、8/120。保留高点较小Raw基线，正式优先报告绝对Goodput与数量，补充固定clock条件下的来源/进程敏感性，不改负载、SLO或主统计。

随后一次冻结实际轨迹、源/模型/源码、统计与30单元。Qwen两load Raw/CT三重复12cells先，M/L共同load额外12；实际compiled配对若有未解释ID/finish变化则停止扩展先归因。隔离Gate ON/OFF三对6cells，另一GPUidle，只关经济判断，所有安全准入保留。

每cell360业务、324future；主Goodput为全部warm+future同时满足readiness TTFT与平均TPOT/完整wall。到达、调度、设备和peer条件配对；最终backend drain计时；不把原双请求wave barrier冒称无限并发Poisson。原main启动/catalog展开在clock前，在线准备、见证、失败、队列、日志/评分、idle全部在内。无需为更好结果更改margin、EOS、scope、语法或PSTP。

**GPU执行完成不等于全部实证验收完成。** 最终所有process/source/tenant/request层结果、Native logical work/驻留/队列及不利输出都需归档、独立复算和核Git远程SHA。

首轮预览已交付：`tsc_revision_final_serving_first_repeat_20261019_zh.md`。Qwen两load各18/324编译未来无ID变化，但scope仅1/18通过，22编译业务13full/9zero native hits；共同点wall近1，高点wall略慢但达标8→27。它不是最终三重复效果，不用小Raw基线放大倍率作主结论，也不据此更换条件。

Qwen12cell阶段完成三重复并通过6组跨阶段检查。各load54/972 compiled future无ID变化，common pooled wall .999986×、high .990905×；绝对Goodput分别.126074002→.126569282、.013177818→.023277243req/s。原始每次点值、Raw重复与11个L0下降均保留；仍仅一个获准来源/scope，不以重复/负载数冒充新来源。阶段报告`tsc_revision_final_serving_qwen_completed_20261019_zh.md`不代替最终三模型/Gate分析。

Mistral/Llama另12cell同样已完成，六组编译配对检查通过；compiled future分别54/972、48/972，完整wall合并倍率分别.999372×、.999568×。四组共同210/3888 future进入compiled；这些位置来自重复租户、轮次和进程，不能当作210个独立来源。对应当前小回执为`main24_completion_metadata_v1.json`；完整Goodput、双向质量、native与尾部仍由冻结主分析复核。隔离Gate六单元已经运行，不替换主服务Raw基线。

固定到达时钟也限制wall倍率的解释。事后CPU分析确认，完成全部请求的wall不可能早于最后计划到达；三重复合并的Qwen common即使假设请求处理为零，相对当前Raw时钟的wall倍率也不超过1.005490×，其到达跨度占Raw完整wall的99.454%。该比例不是GPU空闲率。故必须将完整wall与实际Goodput/请求延迟/物理工作并列，不能单凭wall约1判断所有请求工作均未减少。其他点仍有更大余量，尤其Qwen high实际略慢不能被此解释抹去。完整逐点界限、输入SHA与局限见性能/尾延迟报告和`arrival_wall_bound_v1.json`；这是事后解释，不改变原冻结统计或追加负载。

## 8. 工程修复与失败记录

1. 原端口复用、跨Python AST空字段、缺EOS的异常类型未捕获等均单列修复，保存原源、失败、公开freeze和实际派发。只重测未完成受影响实验单位；已完成cell保持不动。
2. Raw见证不完整窄修复只返回INCOMPLETE/L0/0RPC/0commit；正常15条记录回归决策/payload一致。没有放松EOS或margin。
3. Windows派生校验的CRLF及Python3.13/3.10 float-sum/libm差异保留两个CPU失败视图；容量/P95/SLO/load精确一致，arrival offset最大差3.4106e-13秒。实际只读取原Linux冻结SHA，不把本地重生成trace替换进去，也不谎称全字节相同。
4. 一次草稿把“54尾−6失败RPC”误写为48成功注册。已按逐请求表纠正42/6/5/1并保留回执/提交历史；原计时与GPU结果不改。关键检查/发布现按真实返回码顺序执行。

全部决策、依据、成本边界和未经证实假设见`tsc_revision_GPU_execution_decisions_20261018_zh.md`。没有因此另起新算法或扩大研究矩阵。

## 9. 可复核原始交付与当前未完成项

| 完成数据 | 原始压缩archive SHA256 | 独立核验 |
|---|---|---|
| 原TableIII | `9d324d82cbb0262240cc27cab0505f694e9e37b468a2cad3b34a89774162b7cf` | 801 regular成员双端；本地12成本/525controller/4725质量配对复算一致 |
| 机制/Manifest | `39b2ad426f101602bed6706d1d5866665355cde3c8f3b84915c90eca1a7a3c1f` | 254成员；四CSV/summary及233 effect叶值复算一致 |
| 256补充 | `892650450856f621ffa5f0dbbd583e0a1e4ab162cdc82f52851b1fa3a491198e` | 63成员；summary与配套CSV独立一致 |
| 真实Repo | `ad1916813dfdebb510d641dcb77edce4e6fbafda5daff3b8716c0df7e466cfdf` | 63成员；summary与CSV独立一致 |

原始日志、实际IDs、源码postimage、完整环境/模型注册SHA、native链、失败及分析入口保留在各结果根。37个新Raw/服务/Gate单元的最终包要在7+30全部完成、模型stat/runtime/source后验检查、分析和独立复算后才能关闭；目前未宣称已交付该包。

配套三文档：`ContractKV_Contribution_Necessity_Evidence_Matrix.md`、`ContractKV_Reviewer_Experimental_Closure_Matrix.md`、`ContractKV_Service_Performance_and_Tail_Analysis.md`。36条审稿要求覆盖检查已通过；实验完成与正文/引用/排版完成分开，页行映射与正式Response Letter后置。

当前未完成的是Gate六单元、服务完整统计及其最终分析/归档，不是再增加一个证书体系、采样算法、时序防御或生产trace研究线。若新数据出现有效scope内部可复现质量反例，必须先归因和最小修复；否则按本轮有界结果收口，不为追回旧最高数字无限扩展。
