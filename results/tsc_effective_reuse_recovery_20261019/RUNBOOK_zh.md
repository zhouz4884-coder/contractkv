# 有效复用恢复：可恢复执行状态

本轮新授权：统一授权入口的全V5回归、资格漏斗/完整费用审计、最小执行改进与独立验证门槛。旧V5、原Table III和上一轮828业务授权修复均结束且不重启；旧自动化保持暂停。

- 远程8TB根：`/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv`。
- Study：`results/tsc_effective_reuse_recovery_20261019`。
- 实际source/input freeze：`b27e6528b57b6e0f4f41a43f3484c5d1bc67c70e00662a041b0e6ae3f62bbe41`，599文件。
- 实际Linux预检回执SHA：`6702135525ae9c3ccebe2923d53724030073b5392cf62092e4d6621e78ff3153`；复用只读父runtime/完整model SHA清单并重新核stat，不复制权重/runtime。
- 预执行源码/输入已公开：`3dfed444aec3544b2ede41f437f6a8572deedf45`。预检回执另提交后才启动GPU。
- CPU来源准备PID680192已自然结束；不要重复运行。开发4来源与验证6来源分别冻结，验证未产生模型输出。

## 开发执行与停止

三个模型各一fresh-server，Q/M并行后L；每个引擎内三个全V5接线臂各60业务，加新4来源×L1/L2/L3的12候选诊断及20业务。每cell合计200业务，三cell合计600；三个全V5臂共享同引擎但不同短期授权密钥，仅是接线/开发，不作公平fresh-server速度宣称。Known-source wiring、new development feasibility和held-out validation是三类证据。

`scripts/tsc_effective_development_worker_v1.py`验证freeze/实际预检回执后执行；由单次launcher记录worker PID、启动和退出。已有`development_worker_launch_v1.json`或execution state时只观察现有PID/锁/日志，禁止重复启动。检查`development_execution_state_v1.json`、`development_worker_exit_v1.json`及每cell失败记录，不以观察超时当worker死。

任何compiled相对配对Raw的ID/finish变化都停下归因，不能以分数不掉直接放行。基础设施失败保存版本与完整失败attempt；确认原因后才另冻受影响单元，已完成模型不重跑。所有缓存/日志/tmp在8TB；不抢占、不终止不相关GPU任务。

## 开发后决策

先从原始日志独立重算：授权wire/physical hash、HMAC准入、全部业务输入IDs、scope/output/raw/candidate/EOS拒绝、计划/注册区间、完整wall、Raw与compiled输出质量。候选开发要求2/2来源均严格认证并与实际自由生成一致、Raw重复稳定；原L0家族还需要可靠的经济成本输入，不能从可行性直接变成生产资格。

若仅省很少CPU/HTTP准备且没有合法覆盖提升，不强行追加大服务矩阵。若有具体实质改善，再冻结同源同到达的Raw-authorized/V5-authorized/修复授权臂及SLO、来源和重复；不更改独立来源或门槛。保留所有负结果，最终写MD报告、决策台账并Git发布/远程核SHA。正文及Response Letter不在本轮修改。
