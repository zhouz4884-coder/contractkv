# ContractKV Task-Fidelity Validation：输入修复与有限配对验证

更新：当前有效开发版本为 `input_fidelity_development_{head,faithful}_v2`，各冻结 225 个文件。此前公开的 v1（各 221 个文件）未执行任何新输入 GPU 请求，因生成前发现的内部标签问题而保留为未执行原型。原 R4 的 90 单元不改动。

## 目标与边界

本轮修复已确认的任务输入构造缺陷，保留 CALC、Scoped Behavioral Certification、PSTP 和 Service-Template Certificate 四项贡献。原 R4 的 90 个冻结单元继续执行，所有不利结果保留。本记录不是新的实验成功报告；正文与最终 Response Letter 的整合暂缓。

历史 renderer 在词数裁剪时折叠空白，并可能裁掉 RepoBench 的代码补全前缀。问题影响原稿部分主实验及后续补强，不能只称为 R4 的个别输入缺陷。历史输入、实际逐请求输入和标记任务三者的证据边界见 `tsc_revision_phase3_historical_input_audit_zh.md`。原 Table I 的 85.0%/2.4% 尚未恢复数据到统计量的完整来源链，不能标记为已复现。

## 已完成的 CPU 检查

三模型服务 tokenizer 的旧输入预检与 450 条已有实际 Prompt Token IDs 完全一致。完整输入窗口审计覆盖 9,000 个请求条件；50 个来源中，31 个能在三模型共同 16K 窗口中保留全文，19 个需要裁剪可选上下文。该结论不是实际生成、任务质量或性能结果。

新的输入打包器先尝试全文，仅在超窗时按预定的原文首尾段落或代码行裁剪可选上下文。它不读取参考答案、答案位置、输出、分数、margin、认证结果或速度。问题、系统字段和完整 CODE_PREFIX 受保护；保留片段维持原换行与缩进，删去范围、保留范围和哈希均记录。若关键字段仍超窗，应显式记录不支持，不静默裁掉字段或按结果替换来源。

第一轮 CPU 打包保留 31 个全文、裁剪 19 个，耗时 387.446 秒。生成前进一步核查发现，旧 `_ordered_text` 会把片段标签插入原始 segment 内部：10/10 个 CODE_PREFIX 虽能由片段拼回原文，却未连续出现在 CPU 构造的 raw user 文本中。因此该原型未执行 GPU。

修复仅把同一原始 segment 的相邻连续片段合并在一个外部标签下，保留 CALC 节点、顺序、依赖和档位；业务、候选规划及验证均使用同一格式。重新打包 50 个已观察来源后，32 个全文、18 个裁剪可选上下文、0 个关键字段超窗；HotpotQA 全文从 3/10 变为 4/10。每个来源最终检查三模型、10 租户和 10 轮的 300 个请求变体，包含 chat template、raw/选定候选布局及输出预算，并断言完整 CODE_PREFIX 连续出现在两条相应文本中。独立核对还要求每个打包 segment 连续出现在 CPU 构造的 raw 文本中。准备 CPU wall 为 398.909 秒，单列为共享离线输入准备；这些均不是新服务端输出、任务质量或性能结果。

隔离适配器将 CODE_PREFIX 的 volatility 统一为 0、cache_stability 为 1。200 个布局及其渲染文本核对均不变，实际准备路径的 query scope 与预算也不变。因此该类型修正不作为当前低覆盖的原因或收益来源。原冻结代码不修改；保真输入使用 `stable_word_limit=0`，避免再经过空白折叠。

## 已冻结的已知来源开发对照

使用原 R4 fan-out 中事先选定的两个 HotpotQA、两个 RepoBench 来源。它们已被观察，只能称为开发诊断。Qwen 四个新进程单元各含 400 个业务请求，共 1,600 个：旧输入 raw、旧输入 ContractKV、保真输入 raw、保真输入 ContractKV。

四个进程均使用 GPU lane 0、相同 16K 窗口和两请求闭环 readiness 屏障；顺序为旧/raw、保真/ContractKV、保真/raw、旧/ContractKV，使两个条件的 raw/ContractKV 顺序相反。所有业务、在线规划、失败验证、同步等待、评分与日志计入服务 wall；启动与事前基础控制对两路径同口径排除。一次重复不能证明进程间不确定性或总体因果性能效应。

方法、分数、margin、typed metadata scope、单次认证、原 R4 收益校准与发布机制保持不变。RepoBench 仍用原 `one_python_statement` 检查，没有取消语法保护，没有重写模型输出。先观察纯输入修复的作用，才能决定是否需要那一对事先限定的任务契约兼容性开发对照。

当前两个开发冻结各含 225 个文件：

| 条件 | freeze SHA256 |
| --- | --- |
| 旧输入 | `abfc1439e601f483a0a53e9b8b5d2ff7393971c6f8363d3f21e2d5666f30cdb7` |
| 保真输入 | `47258158983f5b2b173f8d3c327c4ae55de42dcf75aea9ac323069b1ee9fc11f` |

冻结不代表已执行。新 GPU 请求必须等待原 R4 全部 90 个单元完成、归档验证通过、相关 GPU worker 退出，以及本轮公开预注册提交得到远端 SHA 核验。

## 输出契约的有限处理

10 个旧 RepoBench 参考下一行中，5 个不符合独立完整 Python 语句要求；但已有 30 次在线拒绝对应带解释文字的输出，不能全部称为错误拒绝。代码前缀本身还包含文件路径、裁剪后的作用域或未闭合表达式，直接拼接后全程序 AST 失败也不是错误输出的证明。

若开发证据确实支持局部适配，最多评估一个预先明确的 prefix-compatible 语法契约，并给它自己的 fresh raw/ContractKV 配对。必须继续拒绝解释性文字和不符合所声明代码上下文的输出；不能简单跳过所有语法检查。模型输出、原评分及行为认证均不改，不用 gold 在线判断，也不依据新的 held-out 结果调整规则。

## 独立验证与收口

既有排除来源的字节及原服务轨迹的规范化哈希已核对：462 个 pre-R4 来源、50 个 R4 来源及额外旧服务来源合并后，共排除 567 个唯一来源；尚未打开候选池进行新验证来源选择。开发后锁定输入协议与方法，再按固定哈希顺序选择 source-disjoint 的 3 个 HotpotQA 和 3 个 RepoBench 来源。只允许共同窗口中关键字段容量资格筛选，并记录每个不支持候选；不按答案可达性、任务准确率、认证覆盖或速度筛选。三模型、三重复、raw/ContractKV 共 18 个单元。原 Mistral/Llama RepoBench L0 保留，不能为了非 RULER 覆盖临时扩大原资格。

报告绝对任务分数、正向/负向/无实质变化、输出与见证分歧、全路由及编译覆盖、拒绝归因、实际前缀命中、全成本与分层尾延迟。保留所有失败，不追求每个模型或 p99 都改善。完成这项有限验证及必要审计后，给出实验停止决定和两份实验文档；仅可复现的核心机制缺陷允许必要局部修复，不再展开新的算法或无限矩阵。

## 证据入口

- `results/tsc_revision_r4/input_fidelity_development_inputs_v3/preparation_record_v3.json`
- `results/tsc_revision_r4/input_fidelity_development_inputs_v3/independent_input_integrity_v2.json`
- `results/tsc_revision_r4/full_input_window_audit_v1.json`
- `results/tsc_revision_r4/code_prefix_contract_audit_v1.json`
- `configs/tsc_revision_r4_input_fidelity_plan_v3.json`
- `results/tsc_revision_r4/input_fidelity_development_head_v2/freeze.json`
- `results/tsc_revision_r4/input_fidelity_development_faithful_v2/freeze.json`
