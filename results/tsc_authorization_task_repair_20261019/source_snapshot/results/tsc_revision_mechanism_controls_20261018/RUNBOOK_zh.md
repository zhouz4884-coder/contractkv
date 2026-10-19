# 第二、三批：有界机制与 Manifest 闭环

本协议在这两批的任何 GPU 输出出现前冻结。第一批原 Table III 的完整成本测量优先运行；不得在其运行时复制大型 runtime、执行模型预检或启动本批 GPU。只在第一批 24 cells 完成、worker 退出且两卡无其他任务时接续。

## 冻结规模与证据对象

- 三个 7B/8B 模型，各三次 fresh-server 进程，共 9 cells。
- 每个 cell：五类语义风险，各两个变体，每个变体有安全和顺序敏感对照，共 20 个 CALC 实际候选。
- 每个候选实际执行 Raw 见证、同输入 Raw 重复、未经认证的同候选、决策后的真实业务请求。最多 720 次行为业务生成、180 次 GPU 验证。
- Manifest 每 cell 另有三个注册拒绝及真实 raw fallback；两组可接受声明分别执行实际 Raw、Raw 重复、行为认证、四类 binding 后真实业务。最多 135 次业务生成、18 次 GPU 验证。
- 合计最多 855 次业务生成、198 次 GPU 验证。两批共享 9 次模型启动，使用完全分开的 salt/namespace。没有跨实验计时或吞吐比较。

五类是 controlled semantic challenge，不能改名为五个真实 benchmark。两个变体不能当成大量独立来源。原始/候选均由实际 CALC 的 `compile_layout(policy=posc)` 检查合法 DAG。风险案例故意保留未被 DAG 显式编码的顺序语义，检验行为准入的额外价值；不声称 CALC 能自动发现所有隐含依赖。

本批使用已有实际 raw-witness、精确 observation scope、逐 token/EOS margin 规则。raw floor=0.0625、candidate/EOS floor=0.125 不变。仅在这项机制诊断中明确跳过经济筛选，让正常/拒绝成本可观测；不改生产收益门禁、部署 family 资格或 PSTP。未经认证候选不称作旧 frozen-safe D1 的部署结果。Raw 与未经认证候选使用私有独立 salt，不能预先填充待认证 namespace。

Manifest adapter 明确调用现有 `registration_errors` 与实际 controlled-client 的 `issue_binding/check_binding` 后才派发真实 compiled/raw 请求。它是本批接线的可信客户端适配器，不冒充已有公共注册网关。PRIVATE 标注、operator 错标、相同/不同私有槽、授权域和版本都保留。所有标记为可公开的合成数据。

## 执行顺序

1. 核对 `freeze_v1.json`、source_snapshot 的逐字节一致性并 commit/push，确认远程 SHA。全部新 GPU 请求仍为零。
2. 在第一批完成后运行 `scripts/tsc_revision_mechanism_worker_v1.py --root <root> --mode preflight`。必须沿用完整 SHA 注册且未变动的模型；克隆 strict R2 backend 到本 study 的独立 runtime，并核对原源码、native 扩展、全部 py/so 清单及三模型 tokenizer/16K 窗口。
3. 取回并发布 `preflight_v1/receipt_v1.json` 和全部元数据，commit/push 核对远程 SHA。
4. 用 `--mode execute --receipt-sha256 <真实回执SHA>` 执行。已有 worker 或锁只监测，不能重复启动。失败完整保留；修复后整 cell 重跑，不续接半个案例。
5. joined analysis 必须核对真实 output/prompt IDs、两次 Raw 的背景差异、分数正负方向、认证阶段与 post-route 输出；逐次连接 backend `verification_cache_blocks_return`、lookup salt/hash/hit，验证拒绝零认证发布、通过提交边界和实际命中。

只读 residency trace 使用原有 hook，不改变返回值、分配或策略。但同步 trace 写盘会增加时间，因此这些成本为诊断运行成本，不提供服务加速或硬 p99 保证。若没有实际通过/实际命中正对照，必须判定该条证据未闭合；不能将“没有发布”自动当成隔离有效。

## 事前决策

- 不为增加分母重复 RULER、HotpotQA 主矩阵、长输出、CI 或模板摊销实验。
- 实际未变的风险案例不能叫坏布局；Raw 自身不稳定、得分上升与下降均保留；观察到 ID 相同不等于普遍安全。
- trusted operator 的错标可能签名有效、行为通过并发布合成私有标记，这是要检验的真实信任边界，不设“全部拒绝”的成功目标。
- 对不同域/版本的 binding 拒绝，仍实际运行 raw；零共享认证发布不等于零后端请求或零私有 APC 状态。
- 若部署前检查发现接口/路径错误，只作独立冻结的兼容修复；不得根据输出调 margin、案例、答案或语义规则。
