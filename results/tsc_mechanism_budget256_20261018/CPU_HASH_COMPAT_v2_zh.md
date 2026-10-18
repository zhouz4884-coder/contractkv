# 执行前的跨 Python AST 哈希兼容修正

v1 Linux 零 GPU 检查在核对 AST 哈希时停止，没有启动模型或发送 GPU 请求。实际 AST 相同部分的结构断言已通过，但 Windows Python 3.13 与服务端 Python 3.10 的 `ast.dump` 包含不同字段；3.13 的函数节点额外含空 `type_params`。直接对这个版本相关 dump 求 SHA 会错误拒绝同一函数。

保留 v1 全部文件与 `CPU_execution_check_failure_v1.json`。新增 v2 脚本及 `freeze_v2.json`，使用显式规范化 JSON 表达 AST，只忽略已经断言为空的 `type_params`；若以后出现非空类型参数则拒绝。原版本内的 AST 一致断言仍保留，文件 SHA 仍是原始字节，不用这个兼容表示替代源代码完整性。

本地 80 个 fake transport / 20 个 fake qualification 的接线回归再次通过。Linux 实际回执需单独检查、取回并在 GPU 前公开。科学协议仍是原 20 病例、三模型各一次、四路同 256-token 预算，其他规则不变。
