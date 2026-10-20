# ContractKV：行为作用域修复决策记录

## D1 — 先修准入连接，不改评分或部署结果

用户上传评估指出部署 compiled 自路径见证被误用于未来 Raw 行为准入。已核对原代码：`register_one` 固定 tenant00/turn0，模型可见 metadata 却随后续请求变化。保留 27 单元、36 次 compiled 掉分和全部 ID 差异。新版本将模板授权与精确请求 Raw 行为记录分离；只有实际 Raw witness、实际 Candidate 自由生成一致、既有 Token/EOS margin 与 PSTP 验证全部满足才能签发严格记录。授权、schema 或部署自路径 PASS 均不能代替这条记录。

## D2 — 不将 64 个唯一输入变成 64 次昂贵认证

先离线统计旧协议每个引擎中的精确输入重复数。唯一请求直接 Raw，不声称取得模板 O(1) 的 Raw 等价资格。新机制验证使用明确声明的精确输入重复负载，保留模型可见 tenant/turn 内容，不合并不同后缀、不删除 metadata。精确作用域随不同输入数增长，模板物理前缀仍可共用；不宣称任意 query 只认证一次。

## D3 — 有界新来源验证与停止条件

开发使用 Qwen/Mistral、两个新 HotpotQA 和一个新 RepoBench 来源，三个 fresh-engine 对照：Raw-authorized、历史 Deployment、Strict-exact。每来源两个精确输入，各重复四次，合计 24 业务/单元、6 单元；额外 Raw/Candidate 参考及认证全部计费。旧 Repo 家族前瞻 L0 保留，不借本轮解禁。来源只按预先冻结种子哈希和容量选取，gold 不参与选择或裁剪。

开发若严格已获准子集出现不能解释的 ID/EOS 差异，或完全没有 QA 资格，停止正式测量并报告失败。若至少一个模型同时具备严格合法资格、实际命中和按八次访问的实测成本空间，则只为该模型运行独立阶段：三个新 QA、一个新 Repo、每来源两个精确输入各重复八次；三臂、两次 fresh-process 重复，最多 12 单元/768 业务。来源提前锁定，规则不据 held-out 调整。指标为完整 wall、TTFT、任务分数、实际新 Prefill 与资格成本；本轮不宣称开放到达容量或新的 SLO Goodput。

该重复负载是显式条件，不是生产重复率测量；原 64 唯一后缀负载不能被新结果替换。若实测成本不能摊销则保留 NO-GO，不扩大矩阵或放宽门槛。正式阶段仍须另行冻结文件 SHA、执行前回执和来源。

## D4 — 资源与旧任务核查

已通过保存的 Credential Manager/known-host SSH 入口确认同两张 RTX3090 的实际 UUID，无 compute PID；旧 27 单元 worker 已完成。新环境、缓存、日志仍限 8TB 卷，复用冻结隔离 runtime，不修改共享运行时、不抢占其他任务。新 worker 启动前再次检查。

## D5 — 首次公开冻结的换行属性修正，推理前逐字节复核

首次加入新 results 目录时 Git 沿用了文本换行规范，导致远程 Git 中 freeze JSON 的字节与本地/部署副本不同。GPU 尚未启动。为新实验目录及脚本增加 `-text`，重新提交原始字节并核查所有冻结文件与 source snapshot 的 Git blob；保留前一提交，不改科学内容、哈希或选样。后续仅使用字节一致的公开提交和实际预检回执启动。
