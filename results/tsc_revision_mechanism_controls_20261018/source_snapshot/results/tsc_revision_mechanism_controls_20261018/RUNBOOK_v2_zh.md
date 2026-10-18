# 当前诊断执行入口：v2

优先于 `RUNBOOK_zh.md` 的入口版本说明。v1 全部保留，第二、三批迄今 GPU 请求为零。案例、数量、CALC、raw witness、margin、PSTP 和评分均不变。

CPU 接线核对发现 v1 的统一生成包装给 Manifest 的 raw fallback 也加了私有 request salt，而原服务客户端在 binding 不通过时实际使用 `cache_salt=None`。额外隔离会遮蔽原生 APC 可能产生的命中，不能冒充原客户端行为。

因此 v2 的 Manifest raw 见证、raw 重复及 fallback 均使用原来的 `None`，不发送额外 cache_salt。通过 binding 的 compiled 请求仍使用 `policy_hash:namespace`。行为必要性诊断的 Raw/unchecked/qualified namespace 隔离保持不变，用于避免未经认证候选预热待认证空间。

这意味着不同授权域的 binding 拒绝之后，raw fallback 仍可能命中原生无 salt 的 APC。需要实际报告这一点，不能将“没有消费那份认证前缀”提升为“整个引擎的所有原生缓存都已经受域隔离治理”。本实验没有新增通用原生 APC 身份网关或时序防御。

使用 `scripts/tsc_revision_mechanism_worker_v2.py`，冻结文件 `freeze_v2.json`，独立预检目录 `preflight_v2`。先 `--mode preflight`，取回元数据与 `receipt_v1.json` 并 commit/push 核对远程 SHA，再用 `--mode execute --receipt-sha256 <实际SHA>`。第一批原 Table III 完成之前不得启动这些操作。

原 v1 的案例/CPU 审计和源代码都是无 GPU 输出的准备版本；v2 是接线保真修正。正式数据只从实际执行版本产生，但全部准备版本与原因都保留。旧 `RUNBOOK_zh.md` 的规模、测量、解释、不可调参要求继续适用。
