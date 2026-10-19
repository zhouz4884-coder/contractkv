# 授权与任务资格修复：原始证据与复算

本轮是V5收口后另行授权的有界工程修复。历史V5结果和旧客户端保持原样。**9/9 GPU单元、828业务及本机独立复算均完成**；334原包成员/81依赖校验通过，summary全值和五CSV字节一致。最终判断见`docs/ContractKV_Authorization_Task_Repair_Report_20261019.md`，Git发布回执另存；本目录同时保留预执行v1、实际执行v2、CPU审计和独立来源冻结。

## 证据组织

- `freeze_v2.json`：实际9单元的81项测量依赖，SHA256为`b67da7d3b05c08c96d0bf36c997f99570f01af6b2350bbac6c9f942f22f3c9f3`。
- `source_snapshot_v2`：实际测量源码；v1从未执行GPU，只在预执行静态审查时发现重复RPC身份后保留并另冻v2。
- `inputs_v1`、`selection_plan_v1.json`：六个真实新来源的盲选、关键字段保留及三模型实际Prompt IDs。来源不重叠按完整context字节检查，不声称语义独立。
- `evidence_package_v1`：最终原始日志压缩包的32MiB分片、完整成员清单和逐成员SHA；不复制模型、runtime环境或缓存。完整压缩包由分片依次拼回。
- `analysis_v1`：原始日志的机器可读汇总与5份CSV；实际交付时由包中保留并在本机独立复算。
- `local_archive_verification_v1.json`、`local_independent_recompute_v1.json`：成功执行后才存在的本机验收回执，不以脚本存在替代执行通过。
- `task_funnel_posthoc_v1.json`、`report_statistics_posthoc_v1.json`：成功执行后生成的事后CPU诊断；不参与在线资格，不用于倒调held-out规则。

## 离线复算（仅CPU，无模型推理）

在仓库根目录，用一个尚不存在的恢复路径执行：

```powershell
python -B scripts/tsc_repair_local_recompute_v1.py --workspace . --package results/tsc_authorization_task_repair_20261019/evidence_package_v1 --restore .artifacts/authorization_repair_restore_v1 --archive .artifacts/authorization_repair_raw_v1.tar.gz
```

入口核对所有分片、完整包和成员SHA，拒绝不安全路径/符号链接/覆盖已有恢复目录；验81项依赖，以归档中的原始分析源重算全部828业务，要求summary全部值和五CSV字节一致。包中同时保留实际执行snapshot及导入所需的字节一致源码镜像。再次复算需显式保留先前验收回执，并使用新的恢复目录/输出版本；不要为方便覆盖历史验收。

上述命令是本轮实际执行入口，仓库现已包含其成功回执。第三方从当前仓库再次复算，可把回执workspace也设为一个全新目录，保留既有交付记录：

```powershell
New-Item -ItemType Directory -Path .artifacts/review_recompute_v1/results/tsc_authorization_task_repair_20261019
python -B scripts/tsc_repair_local_recompute_v1.py --workspace .artifacts/review_recompute_v1 --package results/tsc_authorization_task_repair_20261019/evidence_package_v1 --restore .artifacts/review_recompute_v1/restore --archive .artifacts/review_recompute_v1/raw.tar.gz
```

新回执位于该新workspace的`results/tsc_authorization_task_repair_20261019`，实际raw恢复在`restore`。目录名必须尚未使用；不需要删除或移动仓库已有记录，也不需要模型文件。

## 计量与信任边界

每个fresh-server单元内部不清缓存。三个模型各三次，共九个单元；每单元92个业务、15项资格决定和7个旧身份发送前拒绝。旧路径5请求/上下文，新路径8请求（人工控制另加1请求），业务数和缓存先后状态不同，因此不能将两阶段wall相除称为修复加速。

Cell wall含全部业务、资格、失败等待及域/epoch操作；不含模型加载、server启动、离线packing/tokenization、控制器初始密钥建立。API TTFT单列；次要serial-ready定义在启动后明确记录，第一请求无ready记录。预设11.7s/435ms仅用于此顺序微工作流的描述性SLO统计，不是新开放到达容量。

统一身份只在新可信入口强制执行，backend仍须置于可信入口后。它不检测可信运营者误标私有内容，不提供完整租户机密性或时序防御，不扩大行为认证作用域。RepoBench未确认误拒时保留原语法与继承L0。

同目录原包包含打包时的生命周期快照；最终CPU退出/发布回执在包生成后另存，不把快照中的`RUNNING_PACKAGE`误解为当前运行状态。总报告、信任矩阵和最终发布回执为交付入口。
