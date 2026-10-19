# ContractKV：服务性能、完整费用与尾延迟分析

2026-10-19。五批实证及本地独立复算已经完成。本文件按协议和科学问题组织结果；各批次的时钟、作用域与来源分别报告。正文及Response Letter仍后置，后续不再启动GPU实验。原始包、复算及最终发布凭据见第12节。

## 1. 当前可支持的性能结论

已有证据支持：在授权重复服务和有效行为资格内，合法连续前缀确有实际物理命中，完整服务成本可以产生净收益，模板共享可以显著摊销资格费用。收益大小依赖复用密度、资格覆盖、实际驻留、输出长度与服务到达条件。

同样已经测到：部分原cohort零隐藏收益很小、Mistral直接wall略慢，p99不普遍降低，收紧成本门禁可能减少尾等待却排除可盈利资格。因此“所有模型/所有负载均更快”“compiled资格等于一直驻留”“0个观察退化等于一般安全”均不成立。

## 2. 不同协议分别承担什么证据

| 协议 | 见证与资格 | 时钟/负载 | 已有主要证据 | 不能外推的结论 |
|---|---|---|---|---|
| Deployment-qualified模板服务 | 在明确注册模板/授权轨迹内的部署资格 | 原受控服务、工具slack或固定开放到达，按各原实验定义 | Session/Template资格摊销125→5次，未隐藏成本25.05→3.24ms/request；原同栈D1/D2与SLO工作点 | 不是任意新query逐请求等价证明，不把其中O(1)资格费用外推开放唯一query流 |
| 原TableIII同cohort完整计时重测 | 原历史候选/多级下降与scope不改 | 原策略参数2s/6s保留；新直接wall不抵扣slack | 四配置24cells、4,725future pairs，所有成功/失败/异常计费 | 新计时不是找回July时间戳；旧驱动未留IDs时不借新协议零分歧补造 |
| 原R4 query-qualified闭环 | 实际首次Raw业务见证，有限query scope与回退 | 双请求共享wave的closed-loop readiness | 36cells、27,000业务；2,442 compiled future未见ID变化，全路由33下降保留 | 历史输入词数截断/代码空白适配限制外部有效性；不能拿低覆盖直接判断正常业务适用性 |
| 独立保真query-qualified闭环 | 保真16K、同原严格scope/margin/EOS/PSTP | 新六来源、10tenant/template、三fresh重复 | 三模型完整wall Q1.619×/M1.109×/L1.070×；1,296 compiled future无ID/分数变化 | 这是closed-loop全成本，不是开放到达容量；有4个L0下降，p99不普遍改善 |
| 本轮保真固定到达服务桥梁 | 同严格query-qualified方法与原经济门禁 | 新六来源、6tenant/template、外生双请求wave；Raw-only事前标定 | 7个Raw及24个主服务单元均完成、独立复算；210/3888 compiled future无ID/finish变化 | 合法覆盖低，四个负载/模型组的来源构成Goodput增量区间均跨零；M/L获准Raw参考F1为0，不作有用QA的跨模型主证据 |
| 本轮隔离Gate ON/OFF | 只关经济decide，行为资格/PSTP不变 | Qwen单GPU隔离三对，另一GPU空闲 | 6/6完成，两侧54资格决定、21RPC、54 compiled future，逐项准入结果一致 | 未观察筛除或稳定性能优势；无隔离Raw基线，不借主服务Raw计算隔离加速 |

固定目录中U个获选query scope可跨tenant分摊，但资格建立费用随U增长。本文不把“同一物理前缀可被不同query资格复用”改写成“所有query只认证一次”。

## 3. 原TableIII：完整费用已经实测闭合

A为原residual-slack预算统计，B为全controller零隐藏费用摊销TTFT，C为实际完整service wall。三者不能互换。

| 配置 | 原A TTFT降低 | 新A TTFT降低 | 新B完整controller零隐藏TTFT降低 | 新C wall吞吐均值 | 三进程C范围 |
|---|---:|---:|---:|---:|---:|
| Llama3.1-8B | 29.41% | 29.47% | −0.20% | 1.011551× | 1.009263–1.015763× |
| Qwen3-8B | 37.81% | 31.50% | 10.82% | 1.020224× | 1.004127–1.028826× |
| Mistral7B | 31.72% | 31.78% | 2.00% | 0.993820× | 0.985267–0.998930× |
| Qwen3-14B TP2 | 44.69% | 42.31% | 20.93% | 1.109442× | 1.099322–1.114763× |

C为三次配对倍率算术平均，范围为固定来源进程描述，不是来源总体CI。B用全部future分摊完整controller；C还反映decode、并行请求及原main完整时钟，故B/C方向不必完全相同。

实际525个controller、453次认证HTTP、155次非通过尝试、30次包装异常及60个无RPC的L0 warmup全部留费用。不能以初始metrics条数推导forward次数，HTTP调用也不是kernel数。旧Qwen8B Repo389/r3/turn1在compiled路由出现次级相似度.72→.38，原sanity proxy未标出；该负结果不加入严格保真“0/1296”的分母。

完整报告与原始归档：`docs/tsc_TableIII_fullcost_replay_completed_20261018_zh.md`；`results/tsc_tableIII_fullcost_replay_20261018/`。

## 4. 独立保真闭环：平均收益与p99的不同答案

下表直接读取主18cells的`analysis/performance_comparison_v1.csv`。每模型1,620未来配对，六个独立来源、三个进程重复。wall倍率是该文件的pooled直接wall口径，与F1三次倍率算术平均分别说明。

| 模型 | 完整wall吞吐 | 三次配对范围 | future readiness均值：Raw→Contract ms | future p99：Raw→Contract ms | 编译未来覆盖 |
|---|---:|---:|---:|---:|---:|
| Qwen3-8B | 1.619040× | 1.614757–1.622596× | 4,443.34→2,494.18 | 8,561.77→9,146.63 | 684/1620，42.22% |
| Mistral7B | 1.109072× | 1.107357–1.110186× | 5,158.25→4,534.70 | 9,418.19→9,511.26 | 342/1620，21.11% |
| Llama3.1-8B | 1.070281× | 1.068091–1.071521× | 4,194.66→4,027.27 | 7,851.28→7,905.66 | 270/1620，16.67% |

Qwen有HotpotQA516和RepoBench168个编译未来；M/L编译未来来自HotpotQA。全部1,296 compiled future无ID或分数变化；全路由四次L0下降保留。绝对Raw分数、正分子集与输出ID分别报告，不能把相对保持等同绝对正确。

已有utility audit进一步区分绝对任务质量：Qwen 684/684、Mistral 258/342、Llama 90/270个compiled future具有正的冻结分数。Llama doc109/doc19各90个零分参考、Mistral doc19的84个零分参考仍计入原分母。正分不等于回答语义正确，保持零分参考也不能作为绝对正确性的证据。来源为原主验证的fidelity_utility_audit_v1.json；这里复用既有审计，不重跑实验。

来源簇/进程p99降低率CI分别为Qwen[−56.247,26.802]%、Mistral[−60.576,−0.137]%、Llama[−16.784,0.151]%。所以不能说三个区间都跨零，也不能声称普遍尾部改善。六来源的小簇数与同源租户/轮次相关性需要保留。

### 已有54个尾请求的实际归因

对每个risk-tail进程取其540个future的p99尾部，共54条，全部L0。逐请求恒等式为：

`readiness TTFT = queue-before-controller + controller-to-submit + backend TTFT`。

逐请求表中，42条有前一wave成功注册，6条有失败GPU认证，5条只有未发RPC的scope拒绝决定，另1条没有前序注册。后两类不能从“54−6”推成成功注册等待；五个scope检查仅约4–9ms，也不能用来解释其全部慢时延。同步注册解释了重要的一部分尾部，Raw后端本身的慢请求仍须保留。不把注册工作按等待tenant数重复计算成多份GPU费用。此处closed-loop readiness包含前wave注册传播；新固定到达要从预定arrival计算，不能直接搬同一因果分摊公式。

新固定到达的日志没有精确注册起止时间，因此分析脚本使用“前wave业务结束→当前wave处理开始”的真实区间与注册duration给出队列重叠上下界，不能虚构唯一因果时间线。

来源：`results/tsc_final_existing_evidence_CPU_20261018/analysis_v1/faithful_p99_requests_v1.csv`、`faithful_p99_summary_v1.json`及`faithful_p99_outcomes_recheck_v1.json`。初次草稿的48 PASS推断已更正，原请求与时钟未改。

### 资格覆盖与当前驻留不是同一指标

| 模型 | compiled future | 完整命中已提交prefix | 部分命中 | 零命中 |
|---|---:|---:|---:|---:|
| Qwen | 684 | 672 | 12 | 0 |
| Mistral | 342 | 300 | 0 | 42 |
| Llama | 270 | 135 | 0 | 135 |

10,800条真实业务均匹配native初始观察；4,860未来配对可连接到scheduler与pool。上表不是资格失败率。已有1,440个compiled全业务的实际前缀LCP均覆盖提交边界；少量已知来源的138业务/4认证诊断直接记录13次缺口前的refcount0回收，提交后立即复用12/12完整。它不能回填全部189条历史partial/zero的具体驱逐时刻。

原始probe的running/waiting/pool是请求初始快照，不是全程峰值。Allocator-used、cached-resident和预留VRAM不同；某次used比例较低不能证明缓存工作集始终全部驻留。缺失eviction/recompute/kernel字段不填0。新性能矩阵只用native初始数据与轻量Prometheus，不安装已注明timing unsuitable的重型residency hook。

## 5. 成本门禁修复：开发改善与独立负结果均保留

单次四来源开发条件曾观察到高成本失败认证阻塞。成本适配在开发A/B保留112/360覆盖，调用9→6，Repo p99约10.13→6.17s，完整wall约995.67→983.41s。这个开发点没有被当作推广结论。

随后独立六来源Qwen九cells，Raw/原版/适配各三fresh进程，结果如下；两策略共享同一Raw对照，不增加成两套独立原生样本。

| 指标 | 原版严格保真 | 成本适配 |
|---|---:|---:|
| 编译未来 | 774/1620，47.78% | 258/1620，15.93% |
| 实际GPU认证RPC | 42 | 12 |
| 获准scope-repeat | 27 | 9 |
| 失败RPC累计工作ms | 62,648.23 | 3,520.67 |
| 完整wall s | 3245.633 | 5468.913 |
| 相对Raw完整吞吐 | 1.802658× | 1.069823× |
| readiness p99 ms | 13,386.89 | 8,801.92 |
| 全路由下降>0.03 | 8，均L0 | 6，均L0 |

Raw wall5850.767s、p998793.88ms。适配对原版的全局p99降低点估计34.25%，直接来源/重复CI[−12.145,37.569]%，跨零；吞吐与覆盖明显损失。27个HotpotQA scope-repeat超出旧长度成本表支持域，被其冻结保守规则前置拒绝；这不是模型窗口溢出，也不是已证明行为资格必须拒绝。原版两个正分Raw来源仍有516个保持行为的合法编译未来机会，被成本变体排除。

工程决定已经做出：保留输入保真和原版严格R4为主实测路径，成本适配不替换默认；不在独立测试结果上扩桶、调预算或重新挑源。本轮新Gate ON/OFF测试原经济门禁，不暗中启用这个失败变体。

来源：`docs/tsc_revision_phase3_cost_repair_results_zh.md`及`results/tsc_revision_r4/cost_adaptation_validation_v1/`。

## 6. 原部署服务与模板摊销仍是独立的系统价值

- 同栈安全布局D1 goodput1.472、完整D2为1.428req/s，保留约97.0%性能。D2不承诺比已知安全D1更快；其额外价值是准入、零拒绝发布、身份生命周期和共享治理。D0约.066req/s只作绝对参照，不作21.5×标题。
- Session→Service-Template把验证125→5次，25×调用摊销；未隐藏费用25.05→3.24ms/request，约7.7×成本优势，限于授权重复模板协议。不能把query-qualified的O(U)写成开放query流O(1)。
- 原25tenant/template、80%load、500ms SLO点从原请求重算：Raw .172667764、Contract .830651232req/s；绝对增量.657983469，CI[.538943295,.765225192]；倍率4.810690862，CI[2.847508685,12.606992697]。区间与负载点限定保留，不称整条sweep都4.81×。
- 80个登记tenant identity下530→149 allocator-used blocks、约72%降低，注明原2,386-block pool及实际并发2。它不是80条GPU请求同时执行，也不是减少72%预留VRAM；新16K单元的实际pool另计。

以上是原部署/开放到达证据，不与新六源闭环倍率或本轮Raw推导SLO拼成同协议性能曲线。旧4.81区间的原方法固定cell wall、抽进程并在policy内独立抽session，其统计边界已在原数据重算审计中写明。


## 7. 新固定到达主实验：同协议服务结果

本批是主动增加的服务桥梁，不是审稿人逐字指定的24单元任务。使用另选的3个HotpotQA来源（doc90/131/187）及3个RepoBench项目（humannorm、UHGEval、spira-jira-migration-advanced）；与既有已知集合做精确原文排除，来源选择不看答案、模型分数或资格结果。不将字节不重复称为语义独立。

三模型保持16K内容保真规则，QA预算128、Repo384、greedy、原scope/margin/EOS/输出契约/PSTP与经济门禁。Raw与Contract使用相同到达轨迹、GPU、波次规则与同波次peer条件；第二重复交换GPU/次序。最多两条GPU请求，客户端仍保留双请求wave barrier，不能描述成无限并发Poisson服务。

Raw-only的7个单元、840业务先完成。事前规则冻结common到达率0.178905114、Qwen high到达率0.329195660 req/s；SLO为readiness TTFT≤11700ms且平均TPOT≤435ms。这是当前16K/3090的Raw标定条件，不是原500ms SLA。主Goodput使用全部warm及future达标请求/直接完整服务wall，不能重置为真正提交后的时钟。本批所有dual达标数恰与TTFT-only相同，TPOT阈值在这些实测点没有进一步筛除；未测逐token TBT分布。

24个主单元共8,640业务，4,320业务配对，其中3,888 future配对。下表每行合并3个进程、每策略1,080业务：

| 模型/负载 | 双SLO达标Raw→Contract | 绝对Goodput Raw→Contract req/s | 直接wall倍率 | 编译future |
|---|---:|---:|---:|---:|
| Qwen common | 761→764 /1080 | 0.126074→0.126569 | 0.999986× | 54/972 |
| Qwen high | 46→82 /1080 | 0.013178→0.023277 | 0.990905× | 54/972 |
| Mistral common | 332→338 /1080 | 0.051099→0.051990 | 0.999372× | 54/972 |
| Llama common | 491→494 /1080 | 0.074209→0.074630 | 0.999568× | 48/972 |

预注册的来源/配对进程构成敏感性固定各cell实际wall，只重采样达标分子；它不是新队列或总体容量的因果置信区间：

| 模型/负载 | Goodput绝对增量 req/s | 条件性95%增量区间 |
|---|---:|---:|
| Qwen common | +0.000495 | [−0.012404, +0.012423] |
| Qwen high | +0.010099 | [−0.000593, +0.026079] |
| Mistral common | +0.000891 | [−0.001098, +0.004392] |
| Llama common | +0.000421 | [−0.000335, +0.002163] |

Qwen high的点倍率为1.7664，但Raw只有46个达标请求；10,000次来源/进程重采样有241次baseline为0，因此按原规则不报告ratio区间，不加伪计数、不删draw。仅按3进程抽样的倍率区间较乐观，不能替代上述来源不确定性。四组绝对增量区间均跨零，本批不支持普遍跨来源Goodput加速。

服务器启动与catalog展开在测量前，对两路径相同；在线准备、首次Raw业务、资格成功/失败、日志评分、排队、计划空隙及最终backend drain均在服务时钟内。累计controller与RPC工作不是可相加的并行关键路径。源数据见formal_analysis_v1、formal_goodput_source_sensitivity_v1.json及原冻结formal_protocol_v1.json；最终原始包与全部源均保留。

### 固定到达对wall倍率的数学限制

事后解释分析arrival_wall_bound_v1.json使用原到达和已完成时钟。对全部请求完成的cell，最后计划到达为A，完整wall为W，则W≥A；相对实测Raw时钟R的wall倍率不超过R/A，三次合并上限为ΣR/ΣA。此上界甚至忽略最后请求的正服务时间，不是实际优化、Goodput上界、容量估计或置信区间。

| 模型/负载 | 实测wall倍率 | 当前Raw时钟下的宽松倍率上界 | 到达跨度/Raw wall |
|---|---:|---:|---:|
| Qwen common | 0.999986× | 1.005490× | 99.454% |
| Qwen high | 0.990905× | 1.069952× | 93.462% |
| Mistral common | 0.999372× | 1.082285× | 92.397% |
| Llama common | 0.999568× | 1.102157× | 90.731% |

99.454%是时钟跨度比例，不是GPU空闲率，计算可与该跨度重叠。固定offered load下wall约1不能单独反证减少请求工作；它也不能抹去实际低覆盖、Qwen high略慢或其他组尚未利用的余量。本解释不改变冻结SLO、负载或主统计，不触发额外GPU点。

## 8. 行为保持、绝对质量与资格覆盖

| 模型/负载 | compiled future /全部future | 获准来源 | 对Raw的ID/finish变化 | compiled参考Raw正分 | compiled参考Raw均分 |
|---|---:|---|---:|---:|---:|
| Qwen common | 54/972，5.56% | HotpotQA doc90 | 0 | 54/54 | 0.666667 |
| Qwen high | 54/972，5.56% | HotpotQA doc90 | 0 | 54/54 | 0.666667 |
| Mistral common | 54/972，5.56% | HotpotQA doc187 | 0 | 0/54 | 0 |
| Llama common | 48/972，4.94% | HotpotQA doc187 | 0 | 0/48 | 0 |

主服务210个compiled future未观察到ID/finish变化，但都来自每模型一个获准来源和有限scope；不是210个独立来源。M/L参考Raw的F1为0，因而该新批次不能独自承担“有用QA输出的跨模型服务收益”主张。认证保持的是获得资格的Raw行为，不校验答案语义正确；本表不将正分也当成正确性证明。

全路由future的变化全部保留，报告阈值为Δscore>0.03上升、<−0.03下降，不能拿它作为认证误差容忍：

| 模型/负载 | future配对 | 输出ID变化 | finish变化 | 明显升分/降分 | Raw→Contract均分 |
|---|---:|---:|---:|---:|---:|
| Qwen common | 972 | 18 | 0 | 13 / 5 | 0.323008→0.323504 |
| Qwen high | 972 | 20 | 0 | 14 / 6 | 0.322864→0.323453 |
| Mistral common | 972 | 13 | 0 | 0 / 0 | 0.159254→0.159254 |
| Llama common | 972 | 22 | 3 | 0 / 0 | 0.076704→0.076779 |

这些升降分发生于L0；混合家族的均分只是冻结F1/SequenceMatcher的描述性汇总，不是准确率。三个Raw控制两两比较各972个future位置，ID/finish变化分别为Qcommon16、Qhigh22、M14、L26；Qcommon为7升9降、Qhigh15升7降，M/L无>0.03升降。比较复用相同的三个控制，不能视为独立事件频率试验；也不能据背景波动将所有策略L0差异唯一归为噪声。Qwen已核对的下降变体在相关Raw控制中复现3/5与4/6，其余事件不做唯一归因。

资格拒绝的来源也已分清：

| 模型/负载 | scope-repeat决定 | PASS | exact-observation限制 | margin | 输出契约 | 经济拒绝 | GPU RPC /失败 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen每负载 | 54 | 3 | 24 | 18 candidate/EOS | 9 | 0 | 21 /18 |
| Mistral common | 27 | 3 | 24 | 0 | 0 | 0 | 3 /0 |
| Llama common | 27 | 3 | 18 | 3 raw | 0 | 3 post-reference | 3 /0 |

M/L的Repo家族继承L0，因此不进入这些GPU资格分母。拒绝只是当前证据不足或契约不满足，不证明所有被拒请求重排后一定有害；不能靠放宽scope/margin或事后换源恢复覆盖。

## 9. Gate ON/OFF：完整三重复的中性结果

隔离Qwen使用同六源、同到达和同GPU；仅经济收益分支开关，行为scope、输出契约、margin/EOS、继承L0与PSTP不变。另一GPU保持空闲，未设置隔离Raw基线。

| 指标，合并三进程 | Gate ON | Gate OFF |
|---|---:|---:|
| 业务 / future | 1080 /972 | 1080 /972 |
| GPU认证RPC /其中失败 | 21 /18 | 21 /18 |
| compiled future | 54 | 54 |
| 双SLO达标 | 764 | 764 |
| 绝对Goodput req/s | 0.126560667 | 0.126561792 |
| 完整controller累计工作s | 84.470847 | 84.216761 |
| 三进程p99均值s | 32.534661 | 32.507363 |

54个namespace/query-scope/repeat匹配的资格决定，在issued、failure reason、category、RPC、level与commit字段上逐项相同；1,080业务的输入IDs及路由档位也一致。不是只看相同总数。ON相对OFF的wall点倍率0.999991；Goodput绝对差−0.000001126req/s，来源/过程构成区间[−0.000664106,+0.000664566]，未观察筛除或稳定收益。

ON/OFF另有15个ID/finish差异、7升8降，保留在全路由质量表；不能把它们当经济分支改变了准入的证明。软件开关的CPU检查与实际client_audit证明OFF设置进入了冻结路径，但CPU接线检查不替代GPU效益。

此中性结论限于Qwen该冻结来源/复用密度。Llama主服务日志确有3次post-reference经济拒绝，说明不能把Qwen无筛除外推为所有模型无筛除；未做Llama OFF，不量化其因果收益。原模型上曾有用的frozen-gate lane证据、成本适配的独立负结果均继续保留。

## 10. 尾延迟：上游波次等待、长输出与近期认证分别看

下表是三个cell分布的均值；p99列为三个cell p99的算术平均，不是来源总体置信区间。全部warm/future计入，与第4节只看future的旧闭环表分开。

| 模型/负载 | Mean readiness TTFT Raw→Contract s | Mean backend TTFT s | Mean E2E s | 三进程p99均值s |
|---|---:|---:|---:|---:|
| Qwen common | 9.055→9.343 | 4.178→4.039 | 11.144→11.343 | 33.155→32.771 |
| Qwen high | 59.038→52.326 | 4.201→4.063 | 61.140→54.337 | 117.859→110.571 |
| Mistral common | 61.920→62.077 | 5.177→5.039 | 66.676→66.791 | 195.988→196.741 |
| Llama common | 38.812→39.013 | 3.952→3.874 | 44.127→44.303 | 187.789→188.772 |

来源、tenant及逐请求时序分别见source_summary_v1.csv、tenant_summary_v1.csv、requests_v1.csv。24主cell各取p99尾共96请求，Raw/Contract各48：全部L0，其中38条达到输出预算，88条来自RepoBench。只有1条具有直接前wave注册，注册与其等待重叠上下界均为1.721ms；其余没有该相邻注册。Gate六cell另有24个尾请求，全部L0、无length及直接前注册。

这与旧闭环54尾的42 PASS/6失败RPC/5无RPC拒绝/1无注册不同，不能搬用旧归因比例。新的近期注册不能解释大部分长尾；但仅凭相邻记录也不能排除更早认证工作对后续队列的累计传播。没有精确注册起止时，只报告真实间隙和duration推导的重叠上下界，不补造因果时间线。主96尾的native scheduler等待均值约1.648s，也不能替代全部上游等待。

利用已经验证的到达轨迹与实际processing/submission偏移，事后重建“已到达、尚未开始controller/尚未提交backend”的客户端数量；不模拟替代调度器。瞬间同时就绪的当前两请求也计入，因此没有额外积压时最小峰值可为2。三重复范围如下：

| 模型/负载 | Raw客户端峰值等待数 | Contract客户端峰值等待数 |
|---|---:|---:|
| Qwen common | 10 | 10 |
| Qwen high | 40–46 | 38–44 |
| Mistral common | 26–48 | 26–48 |
| Llama common | 20–32 | 20–32 |

这些实际客户端pending数量与native GPU等待最大1不是同一阶段。它们说明双请求wave入口前存在积压，不能把Native waiting≤1解读为无排队。重建代码/完整每cell数据见actual_client_queue_forensics_v1.json及tsc_revision_final_queue_forensics_v1.py。这是已有日志的描述性分析，不新增实验，也不能据此声称异步调度已修复p99。

## 11. 物理工作、驻留与资源口径

下表命中采用compiled全业务（包括warm），与第8节future分母分开：

| 模型/负载 | compiled全业务 | 完整 /部分 /零命中 | 实际pool blocks | 2秒采样总VRAM最大MiB |
|---|---:|---:|---:|---:|
| Qwen每负载 | 66 | 39 /0 /27 | 1940 | 20764 |
| Mistral common | 66 | 66 /0 /0 | 3550 | 21700 |
| Llama common | 48 | 42 /0 /6 | 2419–2420 | 20994 |

资格仍不保证当前驻留。该批轻量Prometheus采样中running最大2、waiting最大1，已提供num_preemptions_total最大0；这不证明APC从不驱逐，也不是连续峰值。VRAM为模型/缓存等总占用采样，不等于allocator-used或缓存驻留字节，不能据此声称释放相同比例显存。

每负载合并1,080业务的初始logical new-prefill：

| 模型/负载 | Raw业务token | Contract业务token | 认证额外token |
|---|---:|---:|---:|
| Qwen每负载 | 10,658,856 | 10,189,080 | 214,791 |
| Mistral common | 12,904,308 | 12,473,784 | 26,931 |
| Llama common | 10,273,524 | 10,038,228 | 23,199 |

这里来自实际Prompt IDs减初始native prefix hit，认证另列；不是GPU kernel积分、全部preemption重算或GPU秒。chunked-prefill第一轮实际调度token也在原始分析中另列，不能与完整logical need混用。完整wall和SLO仍以真实时钟为准，不能用token减少替代端到端收益。

## 12. 交付、可支持结论与下一步

新原始包SHA为ce8a001e246f04012d56276232ad2b4acb706149dfde60d0155473e649320cfc，234,884,895 bytes、4分片、1,246成员；58个原冻结Root依赖齐全。7+30共37单元、11,640业务已在本地使用未改冻结分析独立重算。两主摘要6,891/934叶值、敏感性135叶值精确；13份CSV字节一致，主摘要JSON仅换行不同，LF归一后相同。重算后1,246原成员再次核SHA不变。发布凭据见final_publication_receipt_v1.json，拼接/恢复见evidence_package_v1/README_zh.md。

结论限定为：合法前缀、行为准入、原子发布和授权摊销各有实证价值；已有授权重复/保真闭环场景可获得完整成本收益。新固定到达来源的覆盖和有用QA证据有限，未支持普遍跨来源Goodput改善；Qwen门禁此批无实际筛除，p99没有通用改善保证。不能将不同协议最高值拼成统一性能曲线。

GPU阶段已结束并释放。后续只整理现有证据、修改正文、再写Response Letter；不为提高倍率追加来源/负载，不放宽scope、margin、EOS或评分，不增加新算法。
