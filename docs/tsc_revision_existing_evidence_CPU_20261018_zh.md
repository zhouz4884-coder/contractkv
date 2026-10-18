# ContractKV：等待正式矩阵期间的既有证据分析

这是对已经归档日志的CPU分析，新增GPU请求为0。结果位于 `results/tsc_final_existing_evidence_CPU_20261018/analysis_v1/`，入口为 `scripts/tsc_revision_final_existing_evidence_CPU_v1.py`。不改任何运行协议，不覆盖已完成结果。

## 保真主验证的尾延迟

核对三个模型、三进程、六来源的4,860个未来请求，逐条满足 `readiness TTFT = backend TTFT + queue-before-controller + controller-to-submit`。从每进程540个future中取经验p99及以上请求，共54条，完整字段在 `faithful_p99_requests_v1.csv`。

54条均为L0，来自HotpotQA；48条紧接获准注册的等待，6条紧接失败GPU认证的等待。前一wave的真实post-business注册时间分别贡献了约3.88–3.90秒（Llama）、4.57–4.58秒（Mistral）、4.50–4.54秒（Qwen）的尾部请求平均等待。这里是各次进程的描述性范围，不是独立来源置信区间，也不是每次注册重复花费了两个租户的时间。

这些最慢请求没有达到输出长度上限。该结果表明尾部等待并不全由失败认证引起；合法、后续有复用价值的注册也会进入下一wave的readiness时钟。不能仅拒绝已知失败来源就宣布修复，也不能将L0路由理解为不承担系统资格等待。具体P99点值是future-only分层统计，不替换原表包含warm/全请求的口径。

目前观察到的是既有同步协议的费用传播，没有从这项分析确认必须另起调度算法的实现缺陷。继续保留已完成成本适配的覆盖/吞吐损失，不据本分析扩大作用域或更改门槛。新增Open-arrival完成后，应按它自己的预定到达时钟重新分析，不能沿用闭环的因果解释。

## Margin：已有轨迹的固定网格

对51个真实GPU认证响应，固定网格为0、0.03125、0.0625、0.125、0.25、0.5、1.0。仅在原始raw/candidate/terminal-stop三个margin均完整时计算共同下界谓词；缺失不填补。输出分母和完整性均在CSV中列明。

该网格不重算scope、输出契约及未执行候选，也不将margin PASS称为新的认证。NarrativeQA doc99仍是单个已知来源：12个控制资格均获准，72个相关配对中36个未来t7配对实质下降。控制重放的candidate最小margin约0.34375，与此前历史0.40625属于不同执行批次；两者都不能证明变化后的raw轨迹被保持。不能把两批数值混为同一次测量，或选择恰好排除该例的阈值作为新独立验证。

## PSTP：复用原有真实故障记录

- Phase16R：真实native scheduler中的prefix-selective注册，六个harness案例；FAIL/INCOMPLETE/CANCELLED对应的新增提交均为0。PASS只提交完整块；原有公共块不属于新发布。
- Phase17：十个真实并发/故障案例，包含同前缀竞争、pass/fail并存、取消、缺失报告和前端断开。非PASS候选新增cache entries及commit tokens均为0。源级故障与不变量检查不冒充所有并发交错或memory-sanitizer证明。
- Phase18：复用compact endpoint及生命周期记录，包括超时、取消、重复ID、关闭期间验证与收尾。各字段保留原始文件及SHA，不从总摘要扩张成未测能力。

这些证据关闭第五批中“是否需要重复PSTP故障压力测试”的分支：目前不重复GPU。第二、三批仍需要其独立的真实认证、发布和Manifest命中数据，CPU复用不能替代它们。

尚待接续：保真输入四级布局分析、独立Open-arrival、经济门禁ON/OFF实际对照及真实RepoBench机制证据缺口。本文不是最终总报告。

## 保真输入的布局阶梯已完成CPU核对

`layout_v1/` 现已完成三个tokenizer、六来源、十轮、L0/L1/L2/L3，共720个完整渲染Prompt和19,440个segment实例。180个L0 Prompt IDs全部逐个等于已经归档的实际服务输入；720个布局均满足声明的DAG并适配16K预算。当前R4使用L2=0.75的冻结配置，不能与历史默认L2=0.50混称。

例如HotpotQA的平均完整块前缀上限从L0的约3.67/4/5 blocks（Qwen/Mistral/Llama）增至L3的838.33/929.33/802 blocks。这些是原样渲染和完整tokenizer后的结构上限，不是实际命中、获准覆盖或加速。Llama HotpotQA的L3、Mistral/Llama RepoBench的L1–L3超出继承家族上限，表中明确标为未授权，不将其当作在线可用路径。

位移只匹配同一segment内字符区间与token ID均完全相同的内部token；排除heading、chat控制与跨边界重分词token，另报匹配分母。完整prefix上限则使用全部实际渲染IDs。没有将R4单候选客户端改成在线四级下降。

本地CPU分析前两次分别遇到Transformers 5.4默认返回BatchEncoding、以及部分chat模板trim首尾空白的接口差异。失败记录保留在两个CPU error JSON中，没有输出实验结果或GPU调用。显式请求ID列表、记录模板trim后，180个实际服务Prompt IDs全部匹配。没有修改被测服务环境、输入或tokenizer文件来迁就本地分析。

## 后端首次调度、块池与实际命中已接线到尾部

`native_tail_v1/` 将18个原始cell的10,800次实际业务与native初次调度记录逐条匹配，并对4,860个配对future补齐后端等待、running/waiting、allocator free/used/total、实际块表和命中。所有原始文件再次核对已有归档SHA；GPU请求增量仍为0。

前述54条尾请求的后端首次调度等待，按模型平均为Qwen 2,088.85 ms、Mistral 2,595.59 ms、Llama 2,137.60 ms。这是实际请求到首次调度的观察区间，不能叫作纯GPU prefill时间，也不能与controller时间相加后再重复计入已包含它的backend TTFT。采样中实际running最多2、waiting最多1；这是请求初次调度时的快照，不是全程连续峰值。

同一future分母下，compiled实际命中也独立复算如下：

| 模型 | Compiled future | 完整认证前缀命中 | 部分命中 | 零命中 |
| --- | ---: | ---: | ---: | ---: |
| Qwen | 684 | 672 | 12 | 0 |
| Mistral | 342 | 300 | 0 | 42 |
| Llama | 270 | 135 | 0 | 135 |

因此资格有效与物理前缀驻留不能合并统计。这里的零命中仍然是获准编译布局的真实执行，已经包含在此前全成本和自由生成统计中，不能删掉或改记为成功缓存命中。它不等于新增认证失败，也不单独证明缓存管理错误。

块表中相同physical block ID在不同观测时刻出现不同已知hash，保存为“可观察的块复用/回收区间”证据，原始前后请求ID和时间均保留。其中9项尾部关联的旧观测来自premeasurement smoke；不能把这些统称为服务负载引起的逐次eviction。其余区间也不提供确切eviction发生时刻或完整次数。原probe的eviction字段明确为unavailable；没有把缺失填为0。allocator-used数量不等于全部驻留cached blocks或GPU显存用量。

下一项性能实验直接复用已有native initial metrics与Prometheus counters，保存队列、池容量及preemption计数。不给性能主测量安装同步写大量block事件的residency诊断hook；该hook原文已限定其timing不用于性能结论。若新数据不能逐案证明eviction因果，只报告可观察的命中损失、工作量和区间证据，不补造GPU因果耗时。

## 双门槛网格与历史0.40625反例已独立复核

`margin_two_floor_v2/` 使用相同事先声明的七点网格，分别改变raw floor与candidate/EOS floor，得到三模型共147行后验敏感性统计。冻结基线(.0625,.125)在51份完整真实响应中对应Qwen 24/27、Mistral 12/15、Llama 9/9 margin PASS，与实际issuance分母对应。将candidate/EOS改到1.0时，在这些已执行响应里分别保留24/24、0/12、3/9个原获准资格；这只是已测响应子集，不能外推全部请求覆盖或成本。

还从R3原始六个policy/raw文件重新核对已知doc99三重复的完整IDs、见证、GPU响应及归档SHA：candidate最小margin确为0.40625，三个未来Raw Prompt各仅改变一个token、长度均2803；编译未来保持原见证IDs，未来Raw改用另一条输出，F1相差−0.04978。维持raw .0625并把candidate/EOS提高至.25，三个旧见证仍都会通过该margin谓词。因此margin不能替代对变化输入的scope约束。

历史0.40625与后来控制实验约0.34375分开保留，不混为同次测量；三重复仍是一个来源/查询，不是三个独立来源。没有根据这个已知反例选择新阈值、重新生成输出或改写当前运行中的准入规则。
