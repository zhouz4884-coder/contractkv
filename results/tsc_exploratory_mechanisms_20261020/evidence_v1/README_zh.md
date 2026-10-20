# 可选机制实验：原始证据与恢复

这是已知来源上的开发机制研究，不是新增独立来源验证或审稿必做矩阵。主业务12cells/384请求；两个Fused单元另有独立计时的故障/重复辅助控制。所有不利结果保留。

`receipt_v1.json` 给出原始压缩包 SHA256/字节数；`inventory_v1.json` 给出659个regular成员的逐字节SHA。模型权重、runtime副本、编译缓存、临时目录和私有SSH helper没有入包。

恢复并独立复算：

```powershell
python scripts/tsc_exploratory_local_verify_v1.py --root . --restore .artifacts/unused_restore_directory
```

目标目录必须不存在，禁止覆盖旧复算。工具核原包和所有成员，检查解包路径，运行归档中的科学分析及真实驱逐hash取证，最后再次核所有原成员。纯CPU，不触发模型加载或GPU。

归档含实际执行冻结源码、worker状态、响应/实际IDs、Native和分配日志、辅助控制、原计时与分析v1/v2/v3源；v1 freeze仅做CPU预检，实际GPU执行是v2。扁平依赖别名与快照是同一文件的恢复布局，不是重复实验。

本仓库另有完成后CPU派生的`prior_capacity_diagnostic_v1.json`、`full_cost_breakdown_v1.json`和独立验收回执；通过对应`tsc_exploratory_*`脚本及本包原始日志可复算。后写的人类报告与Git交付回执不属于上述原始659成员。
