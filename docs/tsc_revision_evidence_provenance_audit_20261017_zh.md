# ContractKV：Table I 溯源、原 Table III 成本与 Manifest 边界核查

日期：2026-10-17。性质：内部研究记录，不是 Response Letter。

## 先给结论

本轮继续找回了原 Table III 的请求记录，并复现了四配置原报表的均值；**没有找回原 Table I 五行数字的测量生成链**。两件事必须分开，不能把前者称为后者的好消息。

| 问题 | 当前证据 | 状态 |
|---|---|---|
| Table I 的 85.0% / 2.4% | 找到更早的写入动作、绘图常量、Git 快照；未找到生成它们的测量表或计算输出 | 原数字未核实 |
| 原 Table III 原报告 | 四配置、三次重复的请求级重算均复现 | 原报告的算术链已恢复 |
| 原 Table III 零 slack 完整成本 | 可重算已记录 RPC 部分；Llama 丢失 33 次中间/失败 RPC 计时，各配置亦有 controller 计时缺口 | 不能声称完整成本全部闭合 |
| Manifest 信任模型 | 定位实际 HMAC 检查调用点，补 19 例 CPU 检查，修正客户端/代理描述 | 实现边界可明确；不是端到端保密性证明 |

当前可复核的正文结构性主表没有为迁就旧数字而改动。本轮未执行 GPU 推理或新性能实验，未改认证阈值、行为作用域、CALC 或 PSTP，未撰写 Response Letter。

## 一、Table I：这次确实找到了什么

### 1. 找到了比 README 更早的写入记录

在与原论文写作相关的 Qoder 任务中，最早可见完整五行表的动作是 **2026-07-19 10:58:14.283 UTC，即香港时间 18:58:14** 的 `Edit`：将 `submission/contractkv_tsc.tex` 中尚未填写的 Background and Motivation 节替换为完整正文和表格。

该动作直接写入：

| 家族 | Stable ratio | Native recovery |
|---|---:|---:|
| RULER | 91.2% | 2.8% |
| HotpotQA | 82.4% | 2.1% |
| NarrativeQA | 78.6% | 1.9% |
| Qasper | 84.1% | 2.4% |
| RepoBench | 88.7% | 2.6% |
| 五家族均值 | 85.0% | 2.36%，四舍五入为 2.4% |

关联任务在该动作之前的 813 条可见工具结果中，未找到完整目标数列的测量输出。这里导出的是可见的编辑动作与表格片段，不包含模型内部推理。

随后 **2026-07-19 11:15:00.587 UTC** 写入绘图脚本，`gen_tsc_figures.py` 第 49–50 行直接赋值两个列表：`[91.2, 82.4, 78.6, 84.1, 88.7]` 和 `[2.8, 2.1, 1.9, 2.4, 2.6]`。这是绘图输入常量，不是统计脚本。

之后才是已知 Git 记录：

- `c377031cb4c6c7f83924a307f1871a1040b53b22`，2026-07-20 23:09:55 +08:00：`README_ContractKV.md` 中已有 85.0% / 2.4%。
- `dcfa7d2f69b2448e579555a65781d2084a1bf568`，2026-07-22 17:51:36 +08:00：跟踪的 TeX 中已有完整表格。

因此，“7 月 20 日 README 首次出现”应改为“目前最早可定位的完整写入发生在 7 月 19 日写作任务”。**这仍不是找到测量出处。**

可复核输出：[写入链 JSON](../results/tsc_revision_evidence_closure_20261017/tableI_lineage/lineage_audit.json)、[首次写入表格](../results/tsc_revision_evidence_closure_20261017/tableI_lineage/first_table_insertion.tex)。

### 2. 继续排查了哪些位置

| 范围 | 本轮检查 | 结果与限制 |
|---|---|---|
| 原 Codex 长会话及关联写作任务 | 定位早期稿件、关联 Qoder 任务、历史子任务记录 | 找到写入动作，未找到对应计算输出 |
| 关联写作工作区 | 绘图 Python、TeX、备份、图片 | 原图使用常量列表 |
| 关联任务 file-history | 44 个历史文件 | 5 个包含旧表的 TeX 快照，不是新测量来源 |
| Git 不可达对象 | 1,745 个 blob，包括 13 个大文件和其中 ZIP 的可读文本成员 | 相关命中是旧 TeX/替换补丁；大文件的数字命中来自其他请求 CSV 等，未找到旧表计算器 |
| 旧服务器项目文本文件 | 有界扫描 1,421 个文件 | 相关命中为本次返修重建脚本，不是原测量 |
| 早期 opportunity census | canonical slots、phase14a v0/v1/v2 | 家族、样本或数值不符；原记录注明离线 LCP 机会估计，不能冒充 live APC |
| 每家族 25 来源的早期服务实验 | 125 来源、五家族，冻结输入哈希匹配 | 实测请求可核对，但重建比例不符，见下 |

搜索范围是当前项目、关联的本地历史任务和已获授权服务器；不代表遍历所有设备、云盘或未保存 notebook。没有发现文件，不等于证明外部文件从未存在。

检索清单：[搜索范围及候选排除](../results/tsc_revision_evidence_closure_20261017/tableI_lineage/search_inventory_v1.json)、[大 blob 与 ZIP 复核](../results/tsc_revision_evidence_closure_20261017/tableI_lineage/large_blob_followup_v1.json)。

### 3. 最像原表描述的一批旧输入，也没有复现旧数字

`tsc_service_sessions_locality_g1_v0.jsonl` 恰好有五家族各 25 个不同来源，冻结承诺在写作动作之前已存在。这使它成为有理由核查的候选，而不是按数字接近程度挑选的样本。

其规范化输入哈希 `bb52011ed1d0210e05b847ef563751fd7df172bf85df75c21466692d8d953b1e` 与旧 commitment 一致。使用旧 runner 的 8K/1500 词配置及 Qwen tokenizer，在 CPU 上重建的 **1,125 个未来请求长度全部等于历史服务日志的实际 prompt 长度**。历史记录没有完整 Prompt IDs，因此不声称 ID 逐项一致。

| 家族 | 重建 stable-body/input | 旧表 stable ratio |
|---|---:|---:|
| RULER | 91.563% | 91.2% |
| HotpotQA | 95.565% | 82.4% |
| NarrativeQA | 95.538% | 78.6% |
| Qasper | 95.291% | 84.1% |
| RepoBench | 97.007% | 88.7% |

五行均不能按原精度复现。该实验还有 marker 服务任务这一协议差别，不能据此将它认作原动机表的数据。结果见 [g1 候选 CPU 核查](../results/tsc_revision_evidence_closure_20261017/tableI_service_candidate/g1_candidate_cpu_v1.json)。

### 4. CHAT_HISTORY 假说如何处理

“多轮历史增长会降低 stable ratio”在数学上成立，但尚无证据证明它解释了原五行结果。已核查的 g1、phase19b 输入与当前返修输入映射没有相应历史段；部分早期 census 的确含历史，但家族和比例不符。

不能因为需要将 99% 降到 82.4%，就反向补造一段历史或改分母。也不能从这些已检查输入推断未知的原测量绝对没有历史。当前结论只能是：**该解释未认证。**

### 5. 关于“是不是编的”和可信度

现有记录能证明数字被直接写入正文，不能证明其测量出处；也不足以判定某个人的意图。继续断言“原数字一定来自真实测量，只是文件没找到”，同样超出了证据。

这是一项真实的可追溯性缺口，应明确处理。不能将无出处数字包装为已核实的“早期快照”，不能保证原数字不影响审稿判断。合理做法是固定证据口径：保留历史稿件和搜索结果，正文使用可复核的独立统计，最终回复中准确说明替换的依据与范围，不声称重现了旧值。

已补充 51 行跨 cohort 统计，分别保留旧 R4 五家族、保真六来源，以及同四开发来源的两种输入构造。它们解释样本、输入结构、token 归属与平均方法的差别，**不用于声称 85.0% 被“重算成”98.520%**。见 [跨口径核查](../results/tsc_revision_evidence_closure_20261017/tableI_crosswalk/crosswalk_audit_v1.json)。

## 二、原 Table III：找回了真实记录，也发现了旧计时的局限

从旧服务器只读取回 Qwen/Mistral/14B 请求与 canary 记录，结合已有 Llama 记录，在相同 session/turn 上配对。取回清单记录路径、大小、读取前后 mtime 和 SHA256。四配置合计 4,725 个未来请求配对、每配置三次进程重复。

| 配置 | 原报告均值复算 | 零 slack，旧分母，已记录 RPC | 零 slack，全未来请求分母，已记录 RPC | RPC 计时/调用数 |
|---|---:|---:|---:|---:|
| Qwen3-8B | 37.81% | 16.81% | 28.91% | 147/147 |
| Qwen3-14B TP2 | 44.69% | 34.39% | 34.39% | 72/72 |
| Mistral-7B | 31.72% | 2.83% | 19.74% | 126/126 |
| Llama-3.1-8B | 29.41% | ≤20.37% | ≤20.37% | 75/108 |

上述百分比均是 mean TTFT reduction 的成本分量重算，**不是完整服务 wall、live p99 或容量测量**。Qwen8/Mistral 旧计算按“获准未来请求数”摊 RPC 成本，另两配置按全部未来请求；所以同时列出两种分母，不选择较漂亮的一列替代原报告。

主要缺口：

- Qwen8、14B、Mistral 分别有 3、3、24 次 raw 见证生成达到长度上限，异常发生在 verifier RPC 之前；RPC 为零不等于整个 canary 没有成本，异常路径没有保留完整 controller 耗时。
- Llama 旧 runner 只保留最后一次成功调用计时，中间失败只存决策；全失败会把 verification_ms 记为 0。三次重复共 108 次调用，仅 75 次有可恢复时长，缺 33 次。一次旧 server log 可核对到 36 次 verify 请求，但没有补足其耗时。
- Llama 的 20.37% 因此只能作为缺失成本非负时的乐观上界。不得将缺失时长填零，亦不得用其他模型/新实验的时间补成“实测”。

算术重算已完成，完整历史成本没有全部闭合。若必须获得同一输入的完整 controller 零 slack 实测，需要另行冻结带完整计时的有限重跑；该重跑将是新实验，不是恢复历史日志。本轮没有启动它。

输出：[逐重复 CSV](../results/tsc_revision_evidence_closure_20261017/tableIII_audit/matched_cost_per_repeat_v1.csv)、[成本审计 JSON](../results/tsc_revision_evidence_closure_20261017/tableIII_audit/matched_cost_summary_v1.json)、[取回清单](../results/tsc_revision_evidence_closure_20261017/original_tableIII/retrieval_manifest.json)。

## 三、Manifest：纠正实际执行位置，保留可信声明限制

实际 `issue_binding()` / `check_binding()` 位于 `scripts/tsc_real_task_open_loop.py`，在受信任服务客户端 `request_one()` 选择 compiled/raw 之前执行。未发现与该描述对应的、独立部署的公共鉴权代理。旧稿中将其称作 authenticated deployment proxy 不准确，本轮已纠正。

- 绑定错误禁止选择 compiled，回退 raw；不等于所有错误请求均不发送给后端。
- domain 级证书使用通配 tenant 字段。它不验证任意终端用户所填 tenant label 的成员身份，用户认证、域成员授权与后端入口保护属于受信任应用责任。
- 19 例直接提取实际函数体的 CPU 核查：17 例绑定错误拒绝 compiled；合法绑定接受；同授权域通配规则下更换 tenant label 仍接受。这一例按限制保留。
- 9 例注册 helper 仍是 CPU 证据：7 例不一致声明拒绝，正常声明接受，可信 operator 将私有内容误标为共享仍接受；没有将其说成已接入 live endpoint。
- 哈希/HMAC 证明绑定与字节身份，不证明内容公开；PSTP 的发布检查、客户端绑定、CPU 注册 helper 是不同检查点。原型不实现时序侧信道防御。

输出：[客户端绑定边界](../results/tsc_revision_evidence_closure_20261017/manifest_audit/client_binding_boundary_v1.json)。既有证书范围相关 8 项单元测试通过；它们不代表生产网关或 GPU 隔离实测。

## 四、决定与交付范围

1. 不更改目前可复核的主 Table I，不恢复未核实的 85.0% / 2.4%；旧表与原稿保留。
2. 不把不同 cohort 的结构比例拼成原值复现；新增分家族及同源输入对照放在独立补表。
3. 保留四配置原报告的可复现结果，明确已记录 RPC 与完整 controller 成本不同，缺失时长不插补。
4. 纠正 Manifest 的执行位置和域通配信任边界，不凭空补一个公共鉴权代理。
5. 没有新 GPU 实验；没有修改主性能、自由生成零事件分母或安全准入；Response Letter 仍等待正文确认后再写。

这些决定用于避免继续“换数值、换口径”。无法恢复原来源是需要面对的问题，但不能通过给历史数字寻找一个听起来合理的故事来解决。

## 五、交付核验

正文仍为 12 页，补充材料整理为 8 页；六张主图未改实验数据。新增四张补表为 S-XIX–S-XXII。实测版式检查不允许 overfull、未定义引用或 Type 3 字体；作者简介四分之一页空白预留不变。隔离目录重新生成图、表、聚合与定位文件，正文逐页文字及渲染对照，不将重建成功解释为原测量恢复。

独立重建时发现源文件哈希清单混入另一脚本的生成 JSON，导致清单随运行顺序变化；已将派生输出从该源清单排除，并保留实际源文件哈希。此修正只影响重建元数据，不改变实验数值。
