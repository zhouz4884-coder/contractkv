# 行为作用域修复：执行与恢复

实际科学协议为 `protocol_v3.json`，客户端 `tsc_behavior_scope_client_v3.py`；强制实际前缀校验使用 `tsc_behavior_scope_protocol_v2.py`。v4 worker 只修复预检日志命名并执行该客户端。此前 v1/v2/v3 冻结均保留，未执行模型推理，不计作 GPU 结果。

1. 读取本目录 protocol_v3、input_selection、prior_scope_audit、prior_actual_prefix_audit 和 docs 决策记录。
2. 两张 GPU UUID 和全部 compute PID 必须匹配授权资源；无外部任务才执行。已有 worker/锁/有效 state 时只监测，禁止重复启动。
3. v4 freeze 的 root/source_snapshot SHA 和 Git blobs 均须一致；预检校验模型全量 SHA、父 runtime、隔离客户端 import 后生成实际 receipt。旧 0-byte v2 文件是已记录传输占位，不是成功回执。
4. 实际 v4 receipt 取回、核验、commit/push 后，用 v4 worker `--mode launch`，传真实 freeze/receipt SHA 和公开 commit。只启动一次，自动重试关闭。
5. 开发 6 cells 完成后，用冻结 `tsc_behavior_scope_analysis_v4.py` 复算。同一模型严格 compiled 配对不能有 ID/EOS 差异，必须有合法 scope、物理命中及八次访问实测成本空间。未满足的模型不进入独立阶段。判断只来自已冻结开发门槛；独立来源已预留，不能替换。
6. 有合格模型才构建 validation_jobs_v4/freeze_v4，另行预检与公开实际回执；最多三臂×两重复×两模型 12 cells。评分、输入协议、margin、EOS、CALC 和授权分区不变。
7. 完成后停止 GPU，保留全部 raw/compiled/fallback、失败、normal stop/length、计划与实际 clock、全部认证费用、Native 初始 prefill 事件。不得只分析 PASS。
8. 完整原包逐文件 SHA 归档并本地安全恢复，使用同一冻结分析入口独立复算，summary/pairs/cost projections 完全核对，再写最终 MD 报告、commit/push 和核对远程 SHA。

本轮是声明了 exact repetition 和 round-robin 工作集的闭环验证。不是生产重复率、开放到达容量或硬 p99 保证；原 Deployment 的服务性能不能被追认为新严格准入结果。
