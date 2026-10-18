# ContractKV 三批补强：执行与决策记录

## 当前目标

完成原 Table III 同协议全成本、跨模型多语义认证必要性、合成 Manifest 实际发布/命中三批实验。先保留所有结果并完成 Markdown 总报告，再修改正文和 Response Letter。目标不扩展为新算法研究。

## 已作决策

| 时间（UTC） | 证据与决策 | 边界 |
| --- | --- | --- |
| 2026-10-18 08:51 | 两张指定 UUID 的 3090 均空闲，按已发布 v3 回执启动 formal_attempt3；supervisor=141324、worker=141325。 | 不抢占其他任务。v3 只修短 IPC 路径；模型、样本、renderer、候选、阈值、scope、评分和策略 slack 不变。 |
| 09:04:49 | Llama 第一次 Raw/Contract 配对完成，450 个未来配对。两路 service wall 为 553.6395 / 548.5580 秒；完整 wall 倍率 1.009263。Contract 的 50 个 controller 合计 134679.15 ms，实际 30 次 raw-reference 函数调用、36 次 verification 函数调用，0 次包装调用异常。 | 仅一次、一个模型的中间结果，不是四配置总结果。另 20 个预冻结 L0 会话也有实际 controller/warmup 费用，不能把“无认证 RPC”解释为零费用。 |
| 首对完成后 | 模型启动至整对结束约 13.6 分钟。总预算继续按 8–12 GPU 卡时、约 5–8 小时给总报告预留，14B TP2 与基础设施异常仍可能改变进度。 | 卡时是各 GPU 占用时间之和；不等同于自然时间或论文中的 client wall。ETA 不是新的实验结果。 |
| 第二、三批首次 GPU 前 | 将后续规模收为 3 模型 × 3 fresh-process，共 9 cells。每 cell 20 个行为候选，每候选四次真实业务；Manifest 另 15 次业务、至多两次认证。总计 855 次业务、最多 198 次 GPU 验证。 | 尚无本批 GPU 结果。受控语义挑战不冒充真实 benchmark；不把未经认证的候选称作原 frozen-safe D1。 |
| 第二、三批首次 GPU 前 | 使用实际 CALC 的合法布局、原 strict pointwise margin 和真实 raw witness。诊断中明确关闭经济筛选，以便测准入本身；候选精确绑定 observation，raw/unchecked/qualified 各自隔离 namespace。 | 不改变生产 family 资格、收益门禁、PSTP 或服务调度；不声称自动在两套证书体系间切换。 |
| 第二、三批首次 GPU 前 | 只接线现有注册 helper 与实际可信客户端的 HMAC binding 函数，随后执行真实后端请求和 PSTP；使用原有只读 residency hook 核对提交、盐、块链与命中。 | 这是受控客户端适配器，不是公共注册/IAM 网关。同步 trace 的运行成本只作诊断，不用于加速结论。可信运营者误声明可能实际发布，这个结果不能删。 |

第二、三批的源代码、案例和规则已发布至 `258f96e1af72f687463507906933cb740e00f8dc`。冻结文件 SHA 为 `6fa806899ff76baf20a5441e932ede26311b609e54c5ef5ee110d601a8a2b4e8`。远程 48 份部署文件已校验；仍需在第一批完成后做独立 runtime/tokenizer 预检，发布真实 preflight receipt 才能执行。

随后在任何诊断 GPU 请求之前，源码接线审计发现 v1 给 Manifest raw fallback 附加了原客户端没有的私有 salt。这个差异可能遮蔽原生 APC 命中，因此不采用它提供隔离证据。v2 保留原客户端 Manifest raw 的 `cache_salt=None`，单独记录默认原生 APC 与认证 namespace 的命中。原 v1 文件不变、无 GPU 执行；只在行为必要性诊断中继续使用私有控制 namespace。当前入口改为 `scripts/tsc_revision_mechanism_worker_v2.py`、`preflight_v2`，冻结 SHA 为 `9366e45e7a1d103fa2c8972a4f100d6276de5e58c5a446befa13efe2725c1418`。案例、规模、评分、margin 和原有发布规则均未改变；若跨域 raw fallback 命中无 salt 的原生 APC，必须如实报告，不能叫作整台引擎的域隔离成功。

## 计账与解释规则

原 Table III 并列报告两项：实际完整 client/service wall，以及完整 controller 按全部 future requests 摊销的零 slack TTFT 费用。后者是组件计账，不冒充实测 readiness 分布。原策略使用的 slack 值保留，费用分析不减去任何 slack。

每次 `generate_raw`、`compact_verify` 的返回、失败和异常都保留耗时；每个 canary 有完整 controller。`compact_verify` 包含准备与传输，不叫作纯 GPU 核心耗时。原来只保存最终/成功档位的字段继续保留作历史对照，不填补丢失的旧时间戳。

行为结果同时报告 Raw 自身重复变化、未经认证候选的正/负分数变化、认证决定及认证后真实业务输出。Raw/compiled 得分相同与输出 IDs 相同分别统计；输出不同但得分提高仍不当作严格行为保持。

原 Table III 历史客户端没有完整保存全部 Prompt/Output IDs 的能力，不能从文本相同推导 IDs 相同。第二、三批使用现有 strict streaming transport 保存实际完整 IDs，不篡改第一批客户端来混合两种协议。

## 下一步

第一批 worker 按冻结队列继续四配置、三重复。并行仅做本地分析代码和小型证据整理，不在正式 GPU 时段运行其他模型任务或复制大型 runtime。结束后，第二、三批先做 preflight、取回元数据并发布回执，然后接续。最终统一汇总全部实测与失败。
