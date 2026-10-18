# 端口启动故障后的无重复接续

## 实际差额

2026-10-18 11:02:59 UTC，14B r1 Raw 完成全部250次生成，其中225个future，完整service wall为418.206683秒。11:03:24，原worker在下一Contract单元的 `socket.bind()` 检查中报 `EADDRINUSE`；目录中只有failure文件，没有server/client/launch/requests文件，尚未启动模型或业务。前9对18个单元和该Raw单元共19个完成单元全部保留。

后续只读检查未发现8992端口监听或残留compute进程，普通bind与SO_REUSEADDR bind均通过。最近关闭连接的TIME_WAIT是合理嫌疑，但未捕获报错瞬间的socket所有者，不能写成已证实的唯一原因。

## 决策和授权

用户最新明确要求“不重复准备、重跑或覆盖已经完成的实验”。因此不采用旧编排“任何半对都整对重测”的默认执行规则；只重用完整验收、完整哈希一致的单元，从未开始测量的单元接续。不是续跑部分请求，也不按分数或吞吐选择Raw结果。

原v3 worker、计时客户端、样本、模型、runtime、阈值、候选、scope、slack参与策略、评分、TP2、两卡独占和请求并发均不改。新增很薄的 `tsc_tableIII_continue_unfinished_cells_v4.py` 调用原 `run_cell()`，仅给未执行的五个单元使用事前固定的不同loopback端口。旧worker与失败目录保持不变。

14B r1的新pair目录通过符号链接引用原完成Raw，不复制或改写其结果；Contract用新fresh server。r2仍Contract先、Raw后；r3仍Raw先、Contract后。最终为19个原完成单元加5个新单元，共24个独立fresh-server测量。原Raw与后续Contract之间的基础设施间隔须在报告中单列；它不进入任一路client service clock。

## 不重新准备

复用 `launch_attempt3_preflight` 的既有模型全SHA登记、独立runtime和tokenizer/窗口回执；只核对文件stat及当前runtime/source哈希，不重新下载、复制runtime或计算全部权重。19个完成单元的171个测量文件已登记SHA，开始与结束都核验。

执行清单为 `execution_continuation_v4.json`，SHA256：`b50a8d12fd00591350b68f34532a1afad3b05a60d04d4c3d1d820b28db146c76`。原失败state另存 `execution_state_before_continuation_v4.json`。原freeze和此前preflight不变。

顺序：公开源文件及本清单 → v4 `--mode preflight` → 取回并公开真实 `continuation_v4_preflight/receipt_v1.json` → 带真实 `--receipt-sha256` 执行。已有worker或锁仍只能监测；任何无关GPU任务均等待，不抢占。

完整分析使用 `tsc_tableIII_fullcost_analysis_v3.py`。它按原Table III residual-slack的真实分母定义报告A，按全部新记录报告B/C，保留负收益及全部异常。后两批的freeze_v3、9个cell和预检执行入口不受这项端口接续影响。
