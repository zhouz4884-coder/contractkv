# ContractKV Story V3 — 投稿竞争力与审稿风险审计

审计时间：2026-10-17。**依据**：作者本轮上传的 `ContractKV_story_v3_20261017(1).zip` 内 12 页主文、6 页补充材料、六张 PDF/SVG 及分章节 `.tex`，并核对可访问的 2026-07-25 原投稿工程和原 Major Revision 关注点。这里的数值、实验口径均以作者冻结记录为准。没有运行新 GPU 实验或修改原始结果。

## 综合判定

V3 **明显强于此前整合稿**，已经形成一个可被准确复述的单一主张：*Reusable KV is a shareable service object only when layout admissibility, behavioral evidence and transactional publication are bound to the same validity context.*

相对 2026-07-25 版，V3 在真实输入保真、原始 Token IDs、行为见证、完整成本、方法范围与复现材料上都更强；原稿中较有价值的四配置、服务模板摊销、D0/D1/D2、SLO和密度扩展已恢复。然而，科学证据 **不等于** 所有代码路径拥有相同部署级保证；主文还存在若干可能触发 Reviewer 1/3 追问的精确性问题。最终稿建议先处理下列 P0/P1，再编写最后一版 Response Letter。

## P0 — 修改前不建议定稿

### P0-1 Figure 1 和方法中的 Template Certificate 与 query-scope records 需要完全对齐
- **位置**：Fig.1 顶部右侧 “(4) Template certificate” 内有 `q1, q2 → L* / Hs`；主文 `sections/04_design.tex` 行 48–53、102–112；`05_implementation.tex` 行 8–11。
- **担忧**：部署路径有绑定/HMAC template certificate；R4 query-qualified 客户端使用 `(namespace,q)` 资格记录与 `(namespace,H_s)` 稳定前缀关联，但没有独立部署签名的双证书系统。图目前可能让读者误认为 q1/q2 被嵌入一个真实签名模板证书，或被后端统一强制审查。
- **修改**：图上保留一个 `Template identity / auth / version / epoch` 框；分隔一个 `Query-scope admission records` 列出 `q1 → (layout,Hs)`、`q2 → (layout,Hs)`，再以虚线指向统一 `Physical prefix identity (namespace,Hs)`。**不画两个签名证书或自动切换器**。正文用一个紧凑 comparison table 区分：见证来源、资格键、验证调用摊销、客户端/服务端身份检查路径、适用实验。
- **次要图注**：把 `Private candidate stable only` 换成 `Private candidate KV`；在 commit 箭头处标出 `certified stable full blocks`，避免暗示整个候选 KV 只有稳定部分。

### P0-2 Table II 把两套异质测量并排，易被读成一项 matched slack ablation
- **位置**：`sections/table_deployment_width.tex`；`06_evaluation.tex` 行 23–25；Supplement `table:zeroslack`。
- **担忧**：表内 `Net TTFT slack` 37.81–44.69% 与 `Zero-slack supp.` 17.50/-2.84/7.69/10.59% 来自**不同实验/注册成本测量方式**。审稿人 3 明确要求把原 Table III 的验证成本全部算进同条件结果；同一行的两个值虽然有 caption 声明，仍容易被误认为只是 slack 参数不同。
- **修改**：优先使用两个分别编号/分面表，以醒目 `Original deployment: residual verification accounting` 和 `Independent zero-slack cost supplement` 题头；在方法与回复信中说明后者并非对前者的逐请求配对重算。若作者能从原 frozen runtime cost 账本做出**同一 Table III 请求集合/模型/配置/分母**的 `Δslack=0` CPU 再核算，才可放进同条件表；不能凭估计构造。

### P0-3 Manifest trust 仍未达到 Reviewer 1 希望看到的“独立威胁模型与边界解释”
- **位置**：`sections/08_discussion.tex` 行 13–16，仅约两段；`03_model.tex` P4；`05_implementation.tex` 行 8–11。
- **担忧**：审稿人将“运营者错误把私有段声明成共享稳定段”认定为最高后果场景，要求注册时验证、误配置具体例子、hash 作用说明。V3 报告 CPU helper 的 9 例（7 拒绝、1 合法通过、1 trusted semantic mislabel 通过），并说明非 live endpoint；但篇幅仍不足以解释威胁边界。
- **修改**：独立 `Trust model and manifest registration` 子节，明确（i）受信任的 operator、template registration 允许声明哪些稳定字段，（ii）哪些 syntactic/type/identity 检查会拒绝，（iii）一个错误地将 tenant-private tool output 标为 STABLE 的具体失效场景，（iv）hash/HMAC 只能保证身份/完整性、不能证明公开性，（v）注册 helper 测试与实际部署 endpoint 是不同证据，（vi）允许共享域内部的计时通道风险。可在主文留约 1/3–1/2 栏，详细表在 Supplement。**不声称已实现缺失的保密性验证**。

### P0-4 原稿受审稿人质疑的置信区间与条件必须在最终 Response Letter 精确闭合
- **位置**：新版 Fig.5 80% 点、`VI.E` 及 Supplement；原稿 common RULER macro 95% CI [86.44,86.90]、原稿 92.90 vs 92.62、4.81x 单点及原稿 95% CI [2.85,12.61]。
- **担忧**：V3 删除了部分旧 headline，不能因此认为审稿人的具体质疑自动消失。新稿 80% load 显示 0.173 → 0.831 和 +0.658，但原稿已具备绝对改善的 CI [0.539,0.765]。原稿跨三模型过窄 CI 的构造问题仍需正面说明/撤销，而不是静默换一个表。
- **修改**：在 Fig.5 的 80% 点或正文重新报告已可追溯的绝对 Goodput 增量 CI；一一指出 92.90 和 92.62 是不同试验单元，不能当同一 cell；在 Response Letter 解释为何不再使用过于狭窄的原 RULER macro CI（并给出统计单位/重采样的新处理）；保持三次进程 min–max 与来源簇 CI 的区分。

### P0-5 作者简介与最终页数
- **位置**：`contractkv_tsc_story_v3.tex` 行 54 明确 TODO；主文已有 12 页，补充材料 6 页。
- **风险**：编辑通知要求每位作者 brief biography。现有双栏正文 12 页已经较满，补作者简介可能增加一页。
- **修改**：提前规划可迁入 Supplement 的 1/3–1/2 页内容，完整整合 biographies 并重编 PDF、核对页数与图表字号；准备 clean manuscript、另立 Summary of Changes，并按最终要求处理改动标记。

## P1 — 明显提高竞争力，但不需要新方法

### P1-1 科学故事的第二幕可以有一个精确反例
- **位置**：`sections/01_introduction.tex` 行 8–14；`06_evaluation.tex` 行 76–78。
- **建议**：RAG 具体开场已经很好；在从“重排可能改变行为”进入方法之前，用**一句**原已冻结的 Qwen NarrativeQA `doc99` 后续动态元数据反例（旧资格范围内出现原生回答变化、候选保留证人答案，candidate margin 0.40625）解释为何纯排序和 teacher-forced 单次检查不够。明确这是促成保守 qualifier 的开发反例，不把旧失败当作新方法运行结果。
- **效果**：把创新必要性从抽象假设升级为明确可证伪的系统缺口，仍保持正向论文叙事。

### P1-2 图表打印质量总体合格，但有几处应微调
- **Fig.1**：矢量、专业、很像 TSC 正文图；首先修对象身份语义；减少顶部相邻模块的小字密度。
- **Fig.2**：三个面板分别表示 full wall、实际新 prefill 和平均 readiness，视觉层次正确。可叠加三次 fresh-process 实际点或 min–max 小记号，明确不是跨来源置信区间。现在面板只给点估计，容易让重复精度被误认为外部泛化。
- **Fig.3**：Faithful HotpotQA/RepoBench 3×2 + 明确分开的旧 RULER 条合理，不建议为统一 3×3 重新跑 GPU。最后真实请求序列需提供可追溯 ID/hash 链，已在归档；建议减少样本 ID 的装饰意义，突出 PASS/commit/identical output。
- **Fig.4**：25x 和 7.7x 作为 Service-Template 的主视觉非常合适；D0 的 0.066 做低调基线而非 21.5x 主张，正确。
- **Fig.5**：同一页对比开放到达和 80 身份密度的绝对服务结果有力量；必须持续明示两个负载/时间协议不同，不把 381 blocks 说成全部 GPU 显存节省，更不能暗示 80 同时在 GPU 上执行。
- **Fig.6**：复用密度与工作集访问模式的因果敏感性很清楚；50–75% 只称观察跃迁，而非通用阈值。

### P1-3 补充独立来源层面的分布呈现
主研究每模型有 3 HotpotQA + 3 RepoBench 独立来源，10 租户/10 轮/3 重复不能提高来源数。Supplement 虽然报告来源簇 CI 和模型均值，但最好补一个**实际六个来源 × 三模型**的原生绝对任务分数、编译覆盖、delta 分数、重要 tail 行，或 Qwen/ Mistral/Llama 的逐来源效果图/表。从已有 `fidelity_utility_audit` 和逐来源重算产物进行 CPU 整理即可，不能新挑来源或调整方法。

### P1-4 将论文内的“部署/查询”二协议桥梁写得更节制
目前正文反复解释不同 clock/scope，属于科学必需，但四处以上重复会让论文像辩护。建议一个主文小表 + 一个清楚的段落完成定义，随后使用简洁术语，不在每个段落前重复提醒。这既保住专业性，也保持故事推进。

## V3 已经成熟、应坚决保留的部分

- 统一的可被引用的论文命题：layout + behavior evidence + atomic shared visibility；Service-Template Certificate 给出多租户摊销单位。
- Intro 的 Azure RAG 具体例子以及四贡献对应的章节锚点。
- 实际保真数据：三模型 1.619/1.109/1.070x，全 wall 加入成功/失败认证和等待；获准 compiled future 配对 0/1296 output-ID 分歧（不能宣称绝对 QA 正确）。
- 另一六来源 Qwen 1.803x 和成本适配独立失败，二者不作为同等全模型推广。
- Same-engine D0/D1/D2 + 10/10 harmful candidate rejection + PSTP 零拒绝候选发布、25x calls、7.7x unhidden verification amortization。
- 开放到达 80% 点的 +0.658 req/s 与 80 identities 的 530 → 149 physical used blocks，分别声明不同 SLO 和 workload。
- Fig.3 的独立旧 RULER 横条，不将旧输入/冷+fan-out 混入新保真 3×2 同协议矩阵。
- Supplement 新增的五家族 raw segment order（S-I）、4695 个嵌套 segment 位置分析（S-II）、10–80 租户密度、四方法 matched-native 质量双向统计。
- Negative data/p99/R4 L0/raw-repeat 原因未决、缓存 native eviction 诊断及零新实现补丁，保留但不把其作为抽象/引言主线。

## 对 Reviewer 问题的正文映射

| 关切 | V3 对应证据 | 尚需动作 |
|---|---|---|
| R1 强数据摘要与 92.90/92.62 差异 | Abstract（有绝对值）+ Fig.4/5 | 在 Reply 逐项解释旧工作点；Fig.5 恢复 CI |
| R1 非 RULER 和自由生成 | §VI.B/C；Fig.2/3；长输出 Supplement | 已具主证据；注意六来源独立性 |
| R1 CacheBlend 公平性 | §VI 最后比较；Table S-VIII | 回信不能再主张跨栈速度或112x风险倍数 |
| R1 Manifest trust | §VIII.B CPU helper 9案例 | **扩充独立威胁模型段落** |
| R1 side channel / 325k / KV pool | §VIII.B、§VI.D、Fig.5、正文标注 | 已报告明确边界 |
| R2 创新/文献/复现/输入位置 | §I/IV/VII；Table S-I/II/VI | 完整可复核；方法差异表更直观 |
| R3 raw order / zero slack | Table S-I、Table II、S-V | **不能将不匹配的 zero-slack supplemental measurement 说成原 Table III 同条件成本重算** |
| R3 D1 vs D2 与失败拒绝 | Fig.4 + §VI.D | 已具直接回应 |
| R3 4.81x 单点与 325k CPU | Fig.5 + §VI.D | 保留 80% 点的明确 CI；回信复述作用域 |

## 最小执行顺序（不启新 GPU）

1. 修 Fig.1 证书/查询记录对象语义与 private candidate 标签，追加方法比较小表；
2. 拆清 Table II 两套成本协议，并考虑从同一冻结账本做严格 matched `slack=0` CPU 审计；
3. 补 Manifest Threat Model 与 R1 的真实失效例子；
4. 给 Fig.5 的 80% 点恢复绝对改善 CI，并为旧 CI/92.90vs92.62 建立 Response Letter 响应线索；
5. 整理 source-level 质量、coverage、tail 对照，补作者 biographies / 精简篇幅；
6. 完成最终 PDF 后更新审稿意见—页码—修改/数据项的准确索引，再写最终英文 Response Letter。

**总评**：适合继续精修、无需推倒重写。审稿能否录用取决于方法范围是否讲清、证据是否和主张一一对应以及非独立数据是否正确解释；目前没有依据预测录用百分比。
