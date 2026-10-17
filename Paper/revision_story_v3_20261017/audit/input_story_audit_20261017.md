# ContractKV：2026-07-25 投稿版与 2026-10-17 整合版竞争力审计

依据：作者提供的 7 月 25 日最终 LaTeX+PDF 投稿包、`contractkv_tsc_integrated.pdf`、`ContractKV_revision_integrated_20261017.zip`（主文、附录、六张 SVG/PDF、审计文件）、TSC 原始审稿信，以及仓库中已封存的 R4/保真独立/成本/驻留报告。本审计是**建议**，未改变原始论文或实验协议；新图的 RULER 数据仅在其实际独立历史 R4 协议中解释。

## 总结性判断

整合版确实更严谨：RAG 具体开场、行为见证的两种实测资格机制、PSTP 提交与物理驻留区分、保真 16K 的零 slack 全成本实证、精确 ID 对照、明确安全与数据口径。它同样在竞争力上出现新的可修复缺点：把原稿最独特的 **Service-Template Certificate 摊销和 SLO 服务收益**后置/弱化，抽象成“严格保守协议下仍有一点加速”；在**论文正文**写入了修稿过程语气；删掉了五家族与四模型的整体视角、密度扩展和 frozen gate 机制展示。两版均为12页并不表示新版本在论证上必然更强。

## 六图比较和处理

| 图 | 新整合版优势 | 丢失或误读风险 | 建议动作 |
|---|---|---|---|
| Fig.1 | 真正的可编辑矢量图；raw-order 动态片段遮蔽 DOC、DAG、token/EOS witness、PSTP、query scope 对同一物理前缀的映射均很清楚；比最初AI生成信息图更像系统论文 | 右侧仅 `Reuse identity`，模板证书治理/摊销在视觉上偏弱；PSTP 的精确 LCP/16-token commit 边界不够显眼 | **保留结构，精修 1 轮**：强化 `(namespace, scope)` 决策与 `(namespace, stable-prefix hash)` 物理对象的区别；显示 certified boundary；不要绘制没有实现的独立双签名证书/自动模式切换 |
| Fig.2 | 真正可比的三模型严格全 wall/业务+认证 prefill/未来请求 readiness TTFT，方向一致 | 7月主图有4模型配置、五家族资格图、SLO goodput；现在只见3个7–8B模型和6个源，失去部署规模宽度 | **保留主图**，在主结果表/简短单独服务证据中恢复四配置历史 all-workflow（注明2s/6s slack和历史适配）、Qwen14B，以及同一运行栈 Goodput；不混进严格图柱状比较 |
| Fig.3 | HotpotQA/RepoBench 3×2 保真覆盖矩阵 + 0/1296 ID + witness→PASS→COMMITTED→t3 时间线，直接回应 R1 | RULER 占此前 R4 2442 编译未来的2178，多样性在主图中不可见；但历史 RULER 和新六源不是同协议；每个单栏三模块略拥挤 | **不建议把历史 RULER 直接混进统一的3×3 faithful矩阵**；主图保留3×2，增加独立、明确隔开的 `Earlier R4 RULER` 小横条/脚注：每模型 RULER 726/810（cold 210/270 + fanout 516/540），严格注记旧输入与混合冷/共享协议。更干净则将该条放正文/补表，3×2矩阵保留最强非RULER证据 |
| Fig.4 | 25× fewer calls、7.7× lower unhidden verification cost成为主视觉，正确区分 D1/D2 治理代价和 FAIL 的候选零发布 | 删除了原稿同栈 D0 native APC=0.066 req/s 的绝对参照，读者看不到为何1.428 req/s值得重视；三个细图在单栏略小 | **在(c)加入 D0=0.066的轻量第三项/tick**（保留绝对值、避免夸大的21.5×主标题），同时展示 D1=1.472 与 D2=1.428；(b) 标明零发布对象是 rejected *candidate compiled KV* |
| Fig.5 | 4.81×的0.173→0.831与绝对+0.658呈现成熟；530→149和+381 free blocks、同密度 1.152→11.033更扎实 | 原稿10–80 tenants的完整密度可扩展性曲线不见；SLO两种门限口径相异，用户可能只记得一个80点 | **保留图**；将10–80身份容量/吞吐趋势做一个狭小inset或迁入可查表（主文一句引用）；上部强化两种实验口径、2,386-block池和非同时80并发 |
| Fig.6 | 50–75%观察跃迁、round-robin和Zipf的差异很清楚 | 原稿关于冻结收益门禁2/4 lanes的主机制证据丢失，新稿更聚焦失败的cost-adapt变体 | **保留图**；将原有2/4门禁(+7.04/+10.84s两lane，另外raw路由)作为小表/独立简图或正文证据，避免主文只见成本门禁变体失败 |

## RULER 是否加入 Fig.3？明确决定

历史R4的 RULER（按实际`quality_summary_v1.csv`计算）每模型：single-session compiled 210/270 + template-fanout 516/540 = **726/810（89.63%）**，三模型合计2178/2430。该数据来自**旧输入适配、冷会话和ten-tenant混合来源**；保真主验证HotpotQA/RepoBench来自新六个来源、共同16K输入、仅fanout，不能因为两者碰巧都是810分母就混成同条件3×3 heatmap。R1原本批评过原论文过于依赖RULER；把它画成与非RULER等价反而稀释强补证。

优先选择：**Fig.3(a) 保真3模型×2真实任务矩阵**，在旁边/底部用视觉分隔的“Secondary R4 RULER audit”单行补充，或把RULER单行放Supplement与正文交叉引用。绝不画统一图例让读者推断三任务经过相同faithful16K协议。若未来希望真正同协议3×3，需要新的RULER任务保真、同观察/同预算的独立预注册实验，不应只为图对称而启动GPU。

## 用八条故事标准检验正文

| 标准 | 现状 | 必要修复 |
|---|---|---|
| 1 一个ping | “compilation creates governed shared KV service objects”已存在且清楚 | 全文用**共享状态发布治理**作主命题，模式的差异作为实现语义，不能成为另一个ping |
| 2 一句能被引用的论点 | Introduction 的“evidence and identity permit shared state”不错 | 强化为：“Reusable KV is a service object only when its layout, behavioral evidence, and transactional visibility are governed together.” |
| 3 三幕结构 | 开场和方法障碍充分；最终收益被拆成query-bound和部署两段，强价值没收束 | 顺序从“可复用但不可被APC命中 → 重排可变行为，未认证共享是治理问题 → 编译/认证/发布/摊销在真实服务中奏效”，两类实测协议分别证实同一系统理念 |
| 4 引言四拍 | Azure RAG实例、研究缺口、四贡献都有 | 只需在引言末添加**关键双向证据**（严格全成本+模板摊销/SLO），把详细两个witness模式的复杂度移至IV节 |
| 5 具体开场 | 明显比7月版好 | **保留**具体 query-before-sources 案例；用真实token级gap证据做一次紧凑量化，但不得把群体98%当作特定单例指标 |
| 6 评估是推理 | VI.B已有假设，VI.C/VI.E对应问题，尚有数据罗列和失败变体重篇幅 | 每节先一句机制性预测，紧接已冻结结果，末尾一句可引用结论；负成本候选细节降入Supp，留主文对照结论 |
| 7 给出Lessons | 结尾只88 lexical words，主要重复技术和1.619系列 | 加入系统教训：“admission scope determines shareability; commit governs visibility; locality and residency determine realization”; 总结模板级25×/7.7×及完整服务结果 |
| 8 预防四种拒稿 | 问题真实性、严格准入实测明显增强；创新区别及系统规模视觉反而被削弱 | 相关工作补机制差异对照表/小节；恢复多租户模板价值和D0比较；证据边界不写成每段开头的道歉句 |

## 正文必须调整的表述（正文不是修回报告）

- **摘要/引言**：移除 `p99 does not uniformly improve`（摘要）和 `p99 increases are reported`（引言）之类用于预先防御的结尾；在实验的p99表中诚实陈列，Discussion集中解释。
- **II-B**：删除 `the earlier table's exact numerical provenance was not recovered`，这应出现在逐点Response Letter和可复核审计记录；正文只正向报告**本研究使用的新可复算统计、三分母、适用服务场景**。
- **V-B/VI-D**：避免 `earlier adapter`, `revised renderer`, `old input bug` 的修稿过程口吻。将其变成有意义的**输入构造对照**，说明 fixed-word-cap/whitespace-normalized 基线与 structure-preserving task rendering 的实测影响；具体8/10 gold literal、5/10空前缀负例可迁到Supp。
- **VI-G**：独立成本适配负结果应保留，但不应抢走服务主结果舞台；主文1段客观机制发现、数据引用，完整开发和独立失败放Supp。
- **VIII/IX**：限制集中，不反复作为摘要/引言的结尾。Conclusion应恢复 Service-Template Certificate 的跨租户验证经济性与SLO/物理内存意义，而不只复述三模型吞吐。
- **II与Fig1**：Fig1末尾的`qualified state may outlive residency`可以保留技术含义，但更自然地放作物理机制备注，不与核心的认证/事务发布抢中心。Fig1的模板身份认证对象与query-scope控制记录不应画成两个不存在的独立签名证书。

## 必须和原2026-07-25返修保持明确对应（目前有硬缺口）

1. **R2.6 Segment displacement**：已有CPU分析称4695 segment instances，但整合版`sections/supplement_evaluation.tex`中搜索不到`4695`/`displacement`，Response Letter却宣称已在Supp加入并留 `[TABLE INSERTION PENDING]`；**必须把实际计算表和指标定义插入、或修正回复的完成状态**。
2. **R3.1 Raw order per family**：正文只给RAG Azure代码例子，没有五任务族原始段落顺序表。Reply注明 `[PENDING]`，请使用真实冻结runner/manifest生成并添加，不要用抽象常见顺序虚构。
3. **AE/R1/R3导航**：Response Letter仍引用`§VI.H/§VI.I`、`primary Tables II–VIII`等，当前正文VI仅有A–G、主表为Table I–II。R1.4被导向`VI.D`，实为输入构造、行为保持在`VI.C`。全部审稿条目需要重建真实“审稿意见—修订内容—证据表/图—页码行号”映射。
4. **R1全工作流范围**：原四配置全工作流29.41–44.69%的2s/6s slack数值应清楚保留到Supp和在主文给入口；`92.90%`(D1/D2同栈closure)与`92.62%`(80% load)代表不同实验点，要在Reply直接说明来源，不能只因新版隐藏两数就认为问题已回应。
5. **R2创新比较与完整系统**：与CacheBlend/EPIC/Parrot/Prompt Cache/SGLang的系统性“技术目标—证据治理—事务发布—授权生命周期”对比尚无清晰矩阵；在有限版面可用一张简表或Supplement表+正文总结，不能凭空评价不熟悉方法的全部安全特性。
6. **最终投稿形式**：编辑要求author bios、准确页行定位、引用完整性、附录独立提交。新12页排版PASS ≠ 已包含作者简介/全部正式材料。EIC与AE对颜色标记指示存在冲突，应准备干净稿及单独Summary of Changes并在提交前确认。

## 建议最终证据层次与行动顺序

**主张**：ContractKV 通过证据绑定与事务发布，使合法稳定KV成为授权多租户可复用对象。

**三项主要证明**：(i) 经实际token边界核算的可见前缀缺口；(ii) 严格query见证/zero-slack证实高达1.619×（另一Qwen新来源1.803×）完整wall及0/1296 ID分歧；(iii) 部署模板模式同栈D1/D2治理成本可接受，注册125→5、25.05→3.24ms，请求SLO Goodput绝对+0.658req/s和物理块530→149作为独立服务设置的结果。

**行动**：先修正文的开场/摘要/Conclusion和不可避免的技术语义（只改论文），并恢复两项必要补充表；再对Fig1做一次小范围矢量精修，Fig3追加分协议RULER小条，Fig4补D0绝对参照，Fig5保持数字并用小表恢复10–80租户规模；最后完成Reply所有证据位置的逐项同步。所有旧负结果进入对应数据表/Discussion/补充材料，不覆盖历史证据。当前缺口不要求再跑新的GPU。
