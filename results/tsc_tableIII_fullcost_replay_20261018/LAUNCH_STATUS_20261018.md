# 原 Table III：隔离编排准备进展

原 `protocol_v1.json`、`freeze_v1.json`、六份输入、历史源码和计时驱动均保持原 SHA。本条记录补充当前执行入口，不覆盖先前准备记录。

## 本次 heartbeat 的独立进展

两卡仍有其他任务的进程，因此没有启动模型服务或推理。继续完成了可独立进行的 CPU 编排工作：

- `scripts/tsc_tableIII_fullcost_worker_v1.py`：独立 runtime 副本、模型全量 SHA、离线 tokenizer 窗口预检、独立缓存、fresh server 配对、所有已创建进程的安全收尾、完整 client wall 及最终 backend drain。
- `orchestration_CPU_check_v1.json`：五项基础设施检查通过。包括其他任务占 GPU 时，连模型预检和 server Popen 都不会调用；不会向不同进程组发信号；本实验 API 父进程退出后仍可收尾本实验子进程组。这不是 GPU 结果。
- `analysis_plan_v1.json`：在测量前固定完整费用、全路由质量、失败尝试、重复聚合与历史对照口径。
- `prior_model_registry_v1.json`：独立保存既有三模型 SHA 清单，不在其他工作使用的目录改写全局登记。

CPU 检查中按原 runner 核对了 timeout（Qwen/Mistral/Llama 300s，14B 600s）、Llama 显式原 ladder 和仅 Contract 路径接收 qualification manifest。预发布草稿保留在本机 `.artifacts/tableIII_launch_prepublication_draft*`；这些修正均发生在任何 GPU 测量之前，没有使用新结果选参。

## 等待解除后的步骤

所有 Linux 命令在指定 8TB 卷内的远程项目执行。不要在 Windows 上执行 worker 的 Linux 模式。原有 Credential Manager helper 用于连接；不把密码放到命令或文件中。

1. 核对实际 `execution_state_v1.json`。若有 worker PID，先检查 PID、命令和锁是否确属本实验，只观察已有 worker；不能因 SSH 超时而重启，也不能将复用的旧 PID 当作本实验进程。
2. 先只读运行：

```text
<python> scripts/tsc_tableIII_fullcost_worker_v1.py --root <remote-project> --mode check
```

返回 75 表示有其他 GPU 任务，继续等，不杀、不混跑。返回 0 只说明该时刻可独占，不是已经开始实验。

3. 独占可用时，后台运行 `--mode preflight`，保存启动 PID、stdout/stderr。它逐字节登记所有模型分片，复制既有 serving 分支到本实验 runtime 目录，用历史 hook 安装器只修改副本，检查 tokenizer/窗口。完成时写入 `launch_attempt1_preflight/preflight_receipt_v1.json`，然后退出；没有 GPU 业务推理。
4. 下载预检元数据，核对所有 SHA，归档并提交到 Git，验证远程 commit。核对保留分支与旧补丁的兼容性，不能把新分支的版本号相同当作 July 逐字节身份相同。
5. 将预检回执的实际 SHA 传入执行入口：

```text
<python> scripts/tsc_tableIII_fullcost_worker_v1.py --root <remote-project> --mode execute --preflight-receipt-sha256 <actual-receipt-sha256>
```

如果没有正确回执 SHA，worker 会停在预检完成状态，返回 76，不能进入 GPU 测量。正式开始前仍重新检查模型 stat、runtime 文件 SHA、协议/输入和 GPU 占用。
6. 完成 24 个 cell / 4,725 个未来配对后，状态为 `FROZEN_MATRIX_COMPLETE_PENDING_ANALYSIS`；这仅表示矩阵与计时完备性检查完成，还需分析和总报告。不得提前把它写成“返修全部完成”。

## 异常和复跑

每个 cell、pair 的原日志、失败事件和成本保留。中断半个配对不能续跑成完整 cell。必须先记录基础设施或协议修复，再用新的 attempt 目录完整复跑受影响的配对；已完成有效配对只按时间先后保留，不按收益挑选。方法失败不应伪装成反复重试的基础设施问题。

所有收尾只使用本 worker 明确创建的 process group，不使用端口批量 kill，不终止 RevBatch 或其他任务。正式统计中三次进程 min/max 与来源置信区间分开，原失败费用和新测费用分开。模型计时尚未开始时记录 0；开始后若全量请求数尚未汇总，状态写 unknown/null，不能继续显示 0。
