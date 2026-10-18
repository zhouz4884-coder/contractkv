# 五家族实际 raw 顺序与服务包装：R3.1证据

本记录补齐“五类任务的变化段在哪里”这一具体问题。它区分三种对象：数据记录的存储顺序、实际多轮chat消息顺序、服务性能实验的受控工具观察包装。**下表不作为2026年7月原TableI精确统计链已经恢复的证明。**

## 1. 实际TableI独立测量：3,750条已保存请求

从三份完成日志直接提取已保存的`messages`和`character_spans`，逐份核对completion中的压缩原文SHA；没有重新推理、没有用估计token数代替实际请求。

每家族25条登记记录、三次进程；每家族初轮75条、未来轮1–9共675条。实际历史由之前的真实问题与生成答复组成，未来请求中历史消息数依次为2/4/…/18，每一档每家族75条。以下`HISTORY*`表示完整历史消息块，同类连续span仅为展示而合并。

| 家族 | 初轮实际顺序：每家族75条 | 未来实际顺序：每家族675条 | 未来第一个声明可变块 | 在其后仍含稳定正文的未来请求 |
|---|---|---|---|---:|
| RULER | SYS → SYNTHETIC_CONTEXT → QUERY | SYS → HISTORY* → SYNTHETIC_CONTEXT → QUERY | CHAT_HISTORY | 675/675 |
| HotpotQA | SYS → RAG_CHUNK → QUERY | SYS → HISTORY* → RAG_CHUNK → QUERY | CHAT_HISTORY | 675/675 |
| NarrativeQA | SYS → RAG_CHUNK → QUERY | SYS → HISTORY* → RAG_CHUNK → QUERY | CHAT_HISTORY | 675/675 |
| Qasper | SYS → RAG_CHUNK → QUERY | SYS → HISTORY* → RAG_CHUNK → QUERY | CHAT_HISTORY | 675/675 |
| RepoBench | SYS → QUERY → REPO_CONTEXT → CODE_PREFIX | SYS → HISTORY* → QUERY → REPO_CONTEXT → CODE_PREFIX | CHAT_HISTORY | 675/675 |

`SYS`是实际system消息内容；历史为逐对的user/assistant消息；当前请求是最后一个user消息。对四个QA/检索家族，当前问题位于上下文之后；RepoBench把任务指令放在仓库上下文之前，**完整CODE_PREFIX最后**，保持next-line completion的任务结构。

“声明可变”不表示历史的每个字节每轮都会变化。历史增长、当前user位置和chat framing的变化会使后续文档不再位于同一连续前缀。原生APC仍可能恢复一部分历史；不能将全部原生命中都算成稳定文档恢复。独立测量的`rho_p`只统计实际native命中前缀内、归属于声明稳定正文的token。

五家族未来请求全部保留；统计为3,375/3,375在声明可变块后有稳定正文，不表示这些请求都经过ContractKV认证。该实验只测结构机会与Native APC，不提供编译质量或SLO速度结论。

### 数据存储顺序与实际消息顺序不能混写

保存的源记录中，QA/RULER为`SYS→CONTEXT→QUERY`，RepoBench为`REPO_CONTEXT→CODE_PREFIX→QUERY`。实际TableI协议给RepoBench设置独立system消息，并把任务指令移到代码上下文之前。所以上表采用**实际发送请求**，而不是直接把`sample_prompts.jsonl`字段排列当作service raw order。

入口：`scripts/tsc_revision_final_raw_order_CPU_v1.py`；结果：

- `results/tsc_final_existing_evidence_CPU_20261018/raw_order_v1/actual_request_orders_v1.csv`（3,750行）。
- 同目录`summary_v1.json`（五家族、初轮/未来轮、历史消息数和原始文件SHA）。
- 原测量freeze SHA：`a9a1788b6745a194a29c6c1a1edfea679fbe9351c6b8e06483bc59741c5d4bf3`。

## 2. 服务性能实验：受控TOOL_OBS与增长历史是不同协议

对旧R4的冻结source snapshot执行50来源×10轮的CPU renderer；对本轮新保真六源执行6×10轮。只调用已有构造/渲染函数，验证全部已导入源码SHA；没有tokenizer推断、GPU模型forward、认证或新缓存测量。

以下序列位于服务请求的**user消息体内**。外面另有固定TSC指令的system消息；不要把body中的SYS节点和外层system混为同一个对象。稳定内容的连续同类型pieces仅为表格展示合并。

| 家族 | 旧R4 raw user-body顺序（各100个CPU渲染） | 当前保真桥梁raw user-body顺序 |
|---|---|---|
| RULER | SYS → TOOL_OBS → SYNTHETIC_CONTEXT → QUERY | 本轮桥梁不包含该家族 |
| HotpotQA | SYS → TOOL_OBS → RAG_CHUNK → QUERY | 同类型顺序，保留原正文与空白；30个CPU渲染 |
| NarrativeQA | SYS → TOOL_OBS → RAG_CHUNK → QUERY | 本轮桥梁不包含该家族 |
| Qasper | SYS → TOOL_OBS → RAG_CHUNK → QUERY | 本轮桥梁不包含该家族 |
| RepoBench | SYS → TOOL_OBS → REPO_CONTEXT → CODE_PREFIX → QUERY | 同类型顺序，保留原完整CODE_PREFIX；30个CPU渲染 |

这里的TOOL_OBS为runner事前定义的变化元数据（session/turn/status），不是从生产工具日志采样。该适配器没有增长的CHAT_HISTORY；不将TableI的十轮增长历史实验混入同一个服务时钟或资格作用域。

旧R4的100个Repo渲染中有50个CODE_PREFIX节点文本为空，吻合此前5/10来源被1500词预算裁空的审计；标签仍出现在序列中不代表任务字段存在。当前六源渲染的60个USER_QUERY和30个CODE_PREFIX文本包含检查全部通过，CODE_PREFIX没有空节点。

Repo源记录没有原SYS文本，因此旧R4的100个、当前30个Repo body SYS节点为空；外层TSC system消息仍存在，不能将这一点误报成缺失整个system prompt。

入口：`scripts/tsc_revision_final_serving_order_CPU_v1.py`。同结果目录保存`legacy_serving_order_v1.json`、`faithful_serving_order_v1.json`及每次body hash/导入源码SHA。当前实际GPU请求IDs另由冻结CPU shapes与client audit核对；本CPU顺序表本身不证明资格、命中或速度。

## 3. 真实应用源码例子：条件性的结构依据

固定版本`558ffd397eddcfe4da5c85ebc285796b367eb9b2`的Azure公开示例，消息构造为system→传入history→当前user；当前user模板先放问题，再放Sources。它证明这种“变化输入在后续来源内容之前”的布局存在于实际应用代码中。[PromptManager](https://github.com/Azure-Samples/azure-search-openai-demo/blob/558ffd397eddcfe4da5c85ebc285796b367eb9b2/app/backend/approaches/promptmanager.py#L87-L94)，[user模板](https://github.com/Azure-Samples/azure-search-openai-demo/blob/558ffd397eddcfe4da5c85ebc285796b367eb9b2/app/backend/approaches/prompts/chat_answer.user.jinja2#L1-L10)。

这里的推论是条件性的：**如果**不同请求的后续Sources确有重复，而此前问题或历史不同，连续前缀匹配可能无法恢复那些后续重复字节。源码例子没有测量Sources重复频率、生产流量、租户共享概率或ContractKV加速，也不证明7月旧TableI的85.0%/2.4%来自Azure服务。

本次重新核对上述固定源码并保存两文件、MIT license及SHA。AST检查确认system调用、history循环、user调用分别位于87/90/94行；模板中问题位于Sources之前。原始代码未执行。

来源回执：`results/tsc_final_existing_evidence_CPU_20261018/raw_order_v1/azure_source_v1/source_proof_v1.json`。保留源码与LICENSE用于复核，不能将该用例扩写成五类任务都已有生产trace。

## 4. 可用于正文与Supplement的闭合方式

实际TableI顺序表回答R3.1的“哪个mutable段位于哪里”；独立structural survey回答它带来多大的真实native恢复缺口；受控服务包装另列，服务效果仅由其配对实验回答；Azure固定代码只提供真实应用布局的条件性例子。四种证据分别承担自己的结论，不互相替代。

本轮新增GPU请求为0。没有修改旧输入、重新挑来源、改变预算或认证条件，也没有将新顺序表冒充旧测量lineage恢复。正式论文/Supplement嵌入及Response Letter定位在全部实证完成后进行。
