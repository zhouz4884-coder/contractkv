# 当前诊断入口：v3（尚未运行 GPU）

v1/v2 是保留的准备版本，没有产生这两批 GPU 数据。当前使用 `scripts/tsc_revision_mechanism_worker_v3.py`、`freeze_v3.json`、`preflight_v3`；分析使用 `scripts/tsc_revision_mechanism_analysis_v3.py`。第一批原 Table III worker 不变，仍须先完成其 24 cells。

本次接线审计完成了以下两点：

1. v2 已恢复原客户端 Manifest raw 的 `cache_salt=None`，保留实际原生 APC 命中，不额外提供原客户端没有的隔离。
2. Manifest 路由除了实际 HMAC binding，还必须执行本协议已声明的精确 observation `ScopeValid`。不同私有值即使公共前缀 hash/HMAC 仍匹配，也不属于那次完整 observation 见证；它应走 raw。这不是放宽原家族资格。相同完整 observation 的授权租户仍能实际复用。scope hash 只由实际 raw messages、候选 Prompt IDs、输出预算构造，不读取评分答案或风险标签。

案例、CALC、margin、评分、预算、PSTP 与数量完全不变。共 9 个 fresh-server cell，855 次业务生成、最多 198 次 GPU 验证。新作用域条件是在 GPU 首次运行之前补全预定协议，不是根据输出选出的阈值。控制器将分别记录 binding errors 与 observation scope errors，便于区分授权身份和行为资格。

分析 v3 另外保留：接口响应不确定与明确拒绝的区别、实际后端提交数量、实际完整 Prompt IDs 对离线冻结 IDs 的核对、EOS/finish 差异，以及默认 raw APC 命中的 token 与合成标记覆盖。不能把超时但后端已提交的事件算成“明确拒绝零发布”，也不能把 binding 拒绝直接算成“原生 APC 不共享”。

执行顺序与 v2 相同：完成第一批且资源独占 → v3 `--mode preflight` → 取回并公开 commit/push 真实回执和全部元数据 → v3 `--mode execute --receipt-sha256 <真实SHA>`。所有环境、缓存与日志在 8TB 卷，预检也设置 volume-local HF/Torch/临时路径。已有 worker 或锁只监测，不重复启动。

原始 v1/v2 文档中的纯诊断界限、不能更改冻结案例/门槛、失败保留及不作吞吐外推的要求继续适用。
