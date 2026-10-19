# ContractKV TSC大修：最终补强实验总报告

**实验与独立复算状态：完成，2026-10-19。** 五批冻结实验及两项有界补充已经验收，原始成功/失败记录全部保留；最终Git发布以配套publication receipt为准。这是实验收口报告，不是正式论文或Response Letter。用户已选择停止追加门禁实验；既定六单元在回复前已自然结束，此后不再启动GPU。

## 1. 总目标与当前判断

本轮保留CALC、Scoped Behavioral Certification、PSTP、Service-Template Certificate四项原有机制，检验同一个命题：**结构上重复的内容，只有在布局、行为资格、身份与事务可见性共同受控时，才成为可复用的共享KV服务状态。**

已经取得的实证进展是具体的：

- 原TableIII全费用缺口由同cohort新计时闭合，失败/异常/多级下降不再缺账。
- 依赖合法候选确会改变自由生成；180个受控候选中102个实际变化全部被拒，78个不变候选获准并在后续请求保持。
- 真实Repo代码任务中，Qwen两个来源获得9,712/3,328-token前缀的实际复用；这不是合成赋值案例或纸面token上限。
- Manifest注册→绑定→真实发布→后续命中的链条已实际运行，同时证实可信语义误标及Raw原生APC不受同等隔离的风险边界。
- TableI独立结构测量、原RULER/Goodput统计重算和五家族真实raw顺序已经可追溯，不能再依靠未恢复的旧数值链。

已有保真闭环三模型完整wall收益为Qwen **1.619×**、Mistral **1.109×**、Llama **1.070×**，1,296个获准未来配对没有ID变化；这组证据仍成立。新固定到达桥梁则只获得4.94%–5.56%未来编译覆盖，四组Goodput增量来源敏感性区间均跨零；M/L获准QA参考Raw的F1为0。它没有证明普遍的跨来源服务收益，不能覆盖或替代前者。两组分别回答各自协议下的问题，不能选择高值拼成统一结论。

**收口判断：** 四项机制的结构复用、行为准入、候选零拒绝发布与授权摊销已有直接证据；本轮所需费用、质量和信任边界已能逐条审计。新来源服务外部有效性较弱是实测限制，不以进一步放宽scope、换源或开发新算法作为收口条件。下一阶段优先将现有证据准确整合到正文，再写Response Letter。

## 2. 五批工作与实际执行差额

**这些批次是本项目的工作分组，不是审稿人编号，也不表示每一批都由审稿人逐字指定。**

| 工作 | 与返修的关系 | 通俗问题 |
|---|---|---|
| 已有保真闭环主验证18单元 | 已完成的非RULER、真实自由生成与完整成本证据 | 同样一批业务连续跑完，是否更省总时间、编译后回答是否改变？ |
| 第一批原TableIII全成本 | 直接回应Reviewer3的原样本验证开销/zero-slack问题 | 把成功、失败与异常认证都算上，原结果还省多少？ |
| 第二批多类型机制 | 直接回应认证相对合法重排的必要性与D1/D2问题 | 一个合法布局改变了回答时，系统是否会拒绝发布？ |
| 第三批Manifest闭环 | 直接回应注册、误配置、共享身份与信任边界问题 | 哪些错误能实际阻止共享，哪些仍依赖可信运营者？ |
| 第四批固定到达主24单元 | 后来主动增加的服务桥梁验证；审稿人未指定这套24单元矩阵 | 同一张请求时间表下，有多少业务能在延迟要求内完成？ |
| 第五批新Gate六单元 | 额外的真实门禁控制；并非审稿人逐字指定的六单元任务 | 经济门禁是否真的减少无效认证，代价是什么？已有布局、margin、PSTP与尾部CPU证据另计。 |

第四批沿用相同任务家族（HotpotQA/RepoBench）而另选六个来源，将每模板10个租户的旧保真闭环条件换成每模板6个租户及固定到达轨迹。它没有改变冻结的scope、margin、EOS或PSTP。合法覆盖率与实际缓存命中属于测量结果，不是预先保证的“复用条件”；来源、到达和重复密度同时变化，不能把性能差异唯一归因于其中一个因素。

主动强化的科学价值与返修必要性分别判断。第四批和Gate均已完整自然结束，用户的停止追加选择到达时已无运行中的剩余单元；不伪造提前终止，也不继续补跑。正文应以各协议能支持的结论组织证据，额外控制不能取代已经完成的主证据。

| 批次 | 原科学问题 | 实际规模与状态 | 当前结论 |
|---|---|---|---|
| 1.原TableIII完整成本 | 原部署数字计入全部资格开销后还有多少收益？ | 24/24 fresh-server cells；12配对；4,725 future pairs；完成归档/独立复算 | 四配置直接wall并非都快；A残余slack、B完整controller摊销、C实际完整wall必须分开 |
| 2.跨模型机制必要性 | 合法重排是否仍会改变行为，认证能否阻止不支持的发布？ | 三模型×三fresh重复，180候选、720正式行为生成；与Manifest共用9cells；完成 | 102实际变化、其中30掉分全部拒绝；78获准后0变化；拒绝新增发布0 |
| 3.Manifest/绑定/发布 | 检查实际在哪执行，误标和跨域Raw会怎样？ | 135正式GPU业务、18认证RPC、27注册拒绝控制及72后续请求；完成 | 同域18完整命中；可信误标9/9发布marker；跨域/旧epochRaw各18仍命中marker。非公网IAM/保密分类器 |
| 4.保真固定到达桥梁 | 同协议质量保持能否转化为真实SLO服务收益？ | 7/7 Raw标定、24/24主单元、8,640业务；完整分析/原始归档/本地独立复算完成 | 210/3,888 compiled future无ID/finish变化；完整wall约0.991–1.000×；Goodput来源敏感性区间均跨零 |
| 5.消融与尾归因 | 布局/作用域/驻留/门禁如何共同决定收益和尾部？ | CPU布局/位移/native/tail/margin/PSTP完成；Gate6/6、2,160业务、尾/队列逐请求归因及复算完成 | Qwen ON/OFF各21RPC、18失败、54compiled future；54匹配决定完全相同，未观察筛除或性能收益 |

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
- **既有保真闭环主验证：** 三模型各三fresh-process、六来源。Qwen/Mistral/Llama完整wall倍率分别1.619040/1.109072/1.070281；compiled future分别684/342/270，合计0/1,296 ID变化。参考Raw正分分别684/258/90，正分不等于完全正确；全路由另4次显著下降保留。它是闭环收益，不能称为开放到达SLO容量。
- **驻留与tail：** 已有主18的1296 compiled future中，Qwen672 full/12 partial，Mistral300 full/42 zero，Llama135 full/135 zero。资格不保证当前驻留。54尾请求全部L0，前序42PASS/6失败RPC/5无RPC拒绝/1无注册，不能全部归因一次失败验证。
- **成本适配负结果：** 独立Qwen六源九cells，原版1.80266×、适配1.06982×，覆盖774→258/1620；全局p99点13.39→8.80s但直接区间跨零。已决定不替换默认，不在该held-out上扩成本桶或调阈值。

这些证据回答不同问题，不能把来源、窗口、协议或资格不同的倍率连成因果升级曲线。详见其完成报告和`ContractKV_Service_Performance_and_Tail_Analysis.md`。

## 7. 第四批：固定到达服务桥梁的完整结果

来源按704已知来源排除集及事前hash顺序选择，另三个真实Repo机制项目也排除。新六源为HotpotQA doc90/doc131/doc187，RepoBench humannorm/UHGEval/spira-jira-migration-advanced；精确原文不重复不等于语义独立。16K输入、问题/CODE_PREFIX、空白、评分、scope、margin/EOS与PSTP冻结不变。

先运行7个Raw-only单元/840业务，再按预定公式冻结common与Qhigh到达轨迹、readiness TTFT 11.7s及平均TPOT435ms。每cell六来源×六tenant×十轮=360业务，324future；外部两请求wave屏障保留，native最多2活跃请求。主24cells为8,640业务、4,320全业务配对、3,888future配对；r2设备和次序平衡。在线准备、首次Raw业务、失败认证、等待、空闲和最后drain均计时，启动server/目录展开在两侧clock之前。不是无限并发Poisson或数据中心容量测试。

| 组，三进程合并 | 双SLO达标 Raw→Contract /1080 | Goodput Raw→Contract req/s | 完整wall倍率 | compiled future |
|---|---:|---:|---:|---:|
| Qwen common | 761→764 | 0.126074→0.126569 | 0.999986× | 54/972 |
| Qwen high | 46→82 | 0.013178→0.023277 | 0.990905× | 54/972 |
| Mistral common | 332→338 | 0.051099→0.051990 | 0.999372× | 54/972 |
| Llama common | 491→494 | 0.074209→0.074630 | 0.999568× | 48/972 |

来源/过程构成敏感性95%区间（固定实际clock，Goodput绝对增量req/s）：Qcommon[−.012404,+.012423]、Qhigh[−.000593,+.026079]、M[−.001098,+.004392]、L[−.000335,+.002163]，均跨零。不是重新模拟队列或容量的因果CI。Qhigh点倍率1.7664来自46个Raw达标的小分母；10,000来源抽样有241次Raw分母0，因此比值区间留空，不删除这些抽样或加伪计数。

210个compiled future相对各自Raw和实际见证均0 ID/finish变化。Qwen两负载均只获准Hotpot doc90，54/54参考Raw正分、F1均2/3；M/L只获准doc187，分别0/54和0/48参考Raw正分。后者不能当成有用QA跨模型成功。三模型获准source/scope很少，重复tenant/进程不是独立来源。

全路由future保留Qcommon13升5降、Qhigh14升6降；均在L0。M13、L22个ID变化（L另3个finish变化）但无超过±.03的升降分。Raw重复也出现变化，部分Q下降变体复现3/5和4/6；不能将全部策略L0变化归为背景噪声。完整评分、来源、tenant与请求表均交付。

资格分解：Q每负载54决定=3PASS/24精确observation限制/18 candidate或EOS margin拒绝/9输出契约拒绝，21RPC其中18失败；M27决定=3PASS/24scope限制，3RPC；L27决定=3PASS/18scope限制/3Raw margin/3post-reference经济拒绝，3RPC。M/L Repo继承L0。拒绝表示当前证据不足，不证明每个被拒候选必然有害。

固定到达clock约束了wall解释：Qcommon最后到达跨度占Raw wall99.454%，即使请求处理瞬时完成，倍率宽松上界也仅1.005490×。这不是GPU空闲率，不能掩盖覆盖不足、Qhigh略慢或其他点的余量。Mean/P99、TPOT、E2E、实际prefill、资源和完整界限见性能报告。

## 8. 第五批：经济门禁和尾部归因

隔离Gate ON/OFF六cells完整结束，各三fresh-process、1,080业务/972future，无隔离Raw基线。只关经济收益分支，行为认证和PSTP保持。54个匹配资格决定在issued/reason/category/RPC/level/commit字段完全相同；1,080业务输入IDs和路由档位相同。

- ON/OFF均21实际RPC、18失败、54compiled future、764双SLO达标。
- Goodput 0.126560667/0.126561792 req/s，ON相对OFF wall倍率0.999991；增量区间[−.000664106,+.000664566]跨零。
- 完整controller累计84.471/84.217s；三个cell p99均值32.535/32.507s，未观察筛除或稳定性能收益。
- ON/OFF全路由仍有15个ID/finish变化、7升8降，不删，也不将其当成经济分支改变准入的证明。Gate的108个compiled future只对自身实际见证保持，不能混为新增108个独立Raw配对。

该结果只适用于此Qwen来源/复用密度；Llama主日志确有3次经济拒绝，但没有Llama OFF控制，不能量化其门禁因果收益。不以这个中性结果增成本桶、改scope或再选来源。

新增主24cell的96个P99尾均L0，38个length、88个Repo；只有1个直接前wave注册，等待重叠约1.721ms。即时失败认证不足以解释全部长尾；不能排除更早工作累积传播。客户端pending峰值Raw/Contract分别Qcommon10/10、Qhigh40–46/38–44、M26–48/26–48、L20–32/20–32，与native waiting最大1是不同阶段。新遥测总VRAM采样最大Q20764/M21700/L20994MiB，实际pool1940/3550/2419–2420，不套用旧2386池。全时序、口径和不确定性见D报告及actual_client_queue_forensics_v1.json。

## 9. 工程修复、失败保留与独立复算

1. 端口复用、Python AST兼容、缺EOS异常类型均单列版本、失败和公开freeze；只补未完成受影响单位，完成cell不重测。Raw不完整窄修复返回INCOMPLETE/L0/0RPC/0commit，15条正常记录决策/payload保持。
2. Windows预检CRLF和跨Python浮点差异的两个失败视图保留；没有以本地重生成trace替换Linux冻结SHA。最终实际原始包的独立主统计未使用浮点容差，所有值精确一致。
3. 54旧尾的早期草稿48成功注册已纠正为42PASS/6失败RPC/5无RPC拒绝/1无注册，原计时未改。事后arrival解释最初schema假设失败也单存；修复只读取真实raw承诺，未改实验。
4. 未执行的打包选择器曾漏5个目录外Root依赖；原文件一直存在且SHA匹配，保存旧源后补为58/58实际入包。控制日志另放CPU_tmp避免打包自身变化；传输失败与重试记录保留，不复制模型/runtime。
5. 本地从原始包重新评分/核IDs、时钟、RPC、native，37cells/11,640业务全部验收。正式summary6,891叶、标定934叶、来源敏感性135叶精确；13份CSV字节相同。两summary JSON仅换行不同，LF归一后相同，不声称全部文件原字节相同。复算后1,246原成员SHA再次不变。

源码、决策理由与未经证实假设见tsc_revision_GPU_execution_decisions_20261018_zh.md。基础设施修复不作为新增算法或性能贡献。

## 10. 可复核原始交付与实验完成边界

| 完成数据 | 原始压缩archive SHA256 | 独立核验 |
|---|---|---|
| 原TableIII | 9d324d82cbb0262240cc27cab0505f694e9e37b468a2cad3b34a89774162b7cf | 801成员；12成本/525controller/4,725质量配对复算 |
| 机制/Manifest | 39b2ad426f101602bed6706d1d5866665355cde3c8f3b84915c90eca1a7a3c1f | 254成员；summary/四CSV/233 effects叶复算 |
| 256补充 | 892650450856f621ffa5f0dbbd583e0a1e4ab162cdc82f52851b1fa3a491198e | 63成员；summary/CSV复算 |
| 真实Repo | ad1916813dfdebb510d641dcb77edce4e6fbafda5daff3b8716c0df7e466cfdf | 63成员；summary/CSV复算 |
| 新Raw标定/主服务/Gate | ce8a001e246f04012d56276232ad2b4acb706149dfde60d0155473e649320cfc | 234,884,895bytes，4分片，1,246成员、58原Root依赖；37cells全部独立复算 |

新包分片、inventory和receipt位于results/tsc_task_faithful_open_arrival_20261018/evidence_package_v1；README给出离线拼接/安全恢复/重算入口。本地local_archive_verification_v1.json与local_independent_recompute_v1.json分别证明字节与科学计算，不以哈希替代评分。后验integrity核37cells、11,640业务、22waves、58Root/564快照，模型引用原完整SHA回执并核size/mtime，没有重复搬运权重。

配套B贡献矩阵、C审稿36项矩阵、D性能/尾报告及Trust矩阵完整记录各自证据。最终远程Git交付以final_publication_receipt_v1.json中实际核验的commit/blob为准；原始历史操作状态不回写成新的测量状态。

**实验可以收口，论文尚未定稿。** 没有计划中的GPU单元或独立复算待做。剩余的是正文证据组织、表图嵌入、信任边界表述、引文/版式及最后的Response Letter页行定位。时间通道防御、生产exact-query频率、随机采样和数据中心硬件是未测限制，不能伪装已解决，也不在本轮另开研究线。所有已发现的不利数据继续可查，不为旧最高数字追加实验。
