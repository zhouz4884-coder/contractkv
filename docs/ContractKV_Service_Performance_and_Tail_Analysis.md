# ContractKV：服务性能、完整费用与尾延迟分析

2026-10-18。本文件按**协议与科学问题**组织结果。既有完成实验已核验；新保真固定到达24单元与隔离Gate6单元尚未完成，相关部分明确标为进行中。本文不把closed-loop吞吐写成open-arrival SLO容量，也不把deployment-qualified和query-qualified的资格语义混为一谈。

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
| 本轮保真固定到达服务桥梁 | 同严格query-qualified方法与原经济门禁 | 新六来源、6tenant/template、外生双请求wave；Raw-only事前标定 | 4baseline已完成、3Raw profiles运行，24正式未完成 | 不能提前填Contract速度/Goodput，不与旧500ms点混合 |
| 本轮隔离Gate ON/OFF | 只关经济decide，安全资格/PSTP不变 | Qwen单GPU隔离三对，另一GPUidle | 6正式单元尚未完成 | 无隔离Raw基线，不能借并行Raw构造隔离speedup |

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

## 7. 本轮固定到达：实际参数已冻结，效果仍待执行

4个Raw-only baseline/480回答给出单endpoint容量Cq=.313519676、Cm=.198783460、Cl=.212263461req/s；共同arrival=.17890511444180737，Qwen较高点=.3291956598482794。SLO按事前Raw-P95规则得到TTFT11,700ms、平均TPOT435ms，未读Contract结果选阈值。它不是旧500ms SLA。

3个Qwen Raw profiles已启动但尚未结束；之后24主cell与6隔离Gate cell，每cell360业务/324future。正式先冻结全部实际arrival/源/模型/参数/统计，再执行。Raw/Contract同到达、同双请求wave barrier、同GPU与peer负载，r2换卡/先后；最后backend双idle drain在clock内。主Goodput分母为完整wall、分子为全部warm+future同时满足readiness TTFT和平均TPOT的请求；TTFT-only另列。

正常接收的`length`输出、Raw回退、失败注册、在线LP准备、评分/日志和planned idle都保留。启动、依赖导入、catalog与tenant展开在服务begin前，Raw/Contract一致并明确报告。一次RPC/注册的累计工作不是一份可直接从并行wall中相减的独立GPU费用。

固定计数的指数wave间隔归一化到预定horizon，仍保留原两请求dispatch barrier；不能称作无限并发的自然Poisson服务。正式采用来源簇与三paired进程两个统计层次；零Goodput分母记undefined，绝不加伪计数或删除不利单元。

参数/进程入口见`docs/tsc_revision_final_Raw_calibration_20261018_zh.md`、`docs/tsc_revision_final_serving_calibration_design_20261018_zh.md`和`results/tsc_task_faithful_open_arrival_20261018/`。本节在30正式单元分析、独立复算与归档后更新实际结果，不预写正收益。

## 8. 尚需用本轮数据回答的两个问题

1. 在相同固定到达、相同SLO和完整成本下，新来源的合法复用是否转化为更多实际达标请求？Closed-loop倍率和native token节省不能替它回答。
2. 原经济门禁实际减少了哪些认证、避免了多少无复用等待，是否以丢失有用资格为代价？OFF只关经济条件，scope/语法/margin/EOS/PSTP仍保留；隔离ON/OFF不借用并行Raw制造速度比。

回答后按实际结果收口，不为更漂亮倍率加负载点、放宽作用域或开发新调度系统。
