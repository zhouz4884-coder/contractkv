# 授权/任务资格修复：可恢复执行入口

本轮是用户在V5实验收口后新授权的有界任务。原目标已结束；新目标为授权缓存身份最小修复、Repo契约审计与独立CPU/GPU验证。旧contractkv-table-iii自动化保持暂停，不恢复，不重启旧worker。

## 当前执行身份

- 本地：D:/VLA_QWEN/contract kv。
- 远程8TB根：/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv。
- Study：results/tsc_authorization_task_repair_20261019。
- SSH只用C:/Users/LENOVO/.codex/local-tools/contractkv_ssh_credential.py的ssh_client()。不打印复制凭据，不放参数/源/笔记。
- PY：/home/user/miniconda3/envs/contractkv-cu128/bin/python。
- 正式freeze_v2 SHA：b67da7d3b05c08c96d0bf36c997f99570f01af6b2350bbac6c9f942f22f3c9f3，81项文件。
- 实际preflight receipt SHA：9759e626f7352467d59365f9e7650a6624b3c01f187410a0d42caad3b792cbbc。
- 源码/输入/预检先公开：87cd23c52ec500b89ccba0f7a00fdd6878eb874c。新分析边界/CPU交付工具随后2929ff1、eb8e08f公开。
- 当前launcher650400，worker650401。只读真实execution_state_v2.json和worker_exit_v2.json核状态；PID需核命令，不向旧PID发信号。
- 一次性CPU后处理656409已启动，postprocessing_state_v1.json初始WAITING_FOR_EXISTING_GPU；它等GPU9单元/exit0后才跑模型stat/runtime后验、marker tokenizer坐标、独立原始分析与打包。不要重复运行这三步。

## 范围和现有进度

三模型×三fresh-process=9cell，每cell92业务/15资格决定/7旧身份发送前拒绝，共828业务，最多135 RPC。每引擎内不清缓存，legacy Raw无盐/compiled旧盐与新统一HMAC身份分别运行；新真实六源相同冻结输入/评分/margin/EOS/族档位。声明为顺序微工作流，不是新的open-arrival容量或不同任务量的公平速度对照。

首两cell Qwen_r1/Mistral_r1已完成，各92业务，RPC13/5、stale身份拒绝7/7；工作流wall192.945/241.931秒（不含server启动/离线packing）。其synthetic初步数据：旧跨域/旧证书Raw命中1248/1488，新跨域和新epoch首次Raw均0，各自在本域重复恢复1248/1488；认证前缀1232/1472仍命中；错候选拒绝提交0。这只是初步控制，最终须全9和独立复算验收。

Repo CPU已读旧原包18条件，12早拒中0个可确认的合法片段误拒；不取消one_python_statement、不扩大M/L继承L0。所有输出/代码前缀/实际IDs及AST输入保留。v1协议未执行GPU；v2仅解决两个阶段重复RPC/txn ID，原v1/source_snapshot保留，新source_snapshot_v2不动。

## 收尾路径

1. 只观察当前GPU worker，完成原9cell，不加源/改门槛/改预算或重跑完成cell。
2. 等现有CPU后处理结束。任何失败保留日志与原源，修CPU交付错误不重跑GPU；不能将超时观察当worker死亡。
3. CPU正确会生成marker_token_positions_v1.json、post_execution_integrity_v1.json、analysis_v1/{summary,5CSV}、evidence_package_v1/{package_receipt_v1.json,inventory_v1.json,authorization_repair_raw_v1.tar.gz.partNNN}。
4. 取回分片与metadata，核分片/整体SHA和所有成员；使用scripts/tsc_repair_local_recompute_v1.py在新.artifacts恢复目录从raw重新算，保留原analysis，比较summary全部值及5CSV字节。这个入口目前已实现但尚未对实际原包执行，不提前声称PASS。
5. 输出本轮MD总报告、授权实施/信任矩阵和决策记录，完整保留弱收益/变化/长度/拒绝。source/margin/原PSTP逻辑不变。若新实际Repo中出现可确认误拒，只作诊断记录，不能倒调这个held-out规则。
6. 显式add本轮文件，保留用户Paper未跟踪及两旧删除；commit/push核远程SHA与blob。实验完整后再决定正文整合；不写Response Letter、不新增调度算法或无限GPU矩阵。

## 安全与计时边界

新修复在统一可信授权入口生效，旧无盐入口作为V5控制保留，不能声称公共backend自动验证外部用户身份。盐按engine/policy/template/domain/active-epoch派生；域应等于可共享Native APC状态的实际信任组，不能自动发现语义私有内容或错误/过宽的域配置。epoch检查是可信派发时检查，不擦除已有块、不中断在途请求，不提供跨控制器持久撤销服务。需要更强机密性时仍需恰当部署/独立引擎；本轮不是时序攻击或完整隔离证明。

单请求API TTFT和包含前序资格等待的serial ready时延分别报告；第一请求无精确ready日志，不重建时间戳。该次要口径在启动后明确记录secondary_clock_definition_v1，阈值11.7s/435ms未改，不冒称全统计定义均早于GPU。主要授权/块链假设、来源/规则和停止条件全部先冻结/发布。
