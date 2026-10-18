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
