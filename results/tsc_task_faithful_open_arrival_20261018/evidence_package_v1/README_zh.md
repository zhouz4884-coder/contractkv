# ContractKV 新服务原始证据：离线恢复与独立复算

2026-10-19。此目录保存实际GPU运行所得原始日志的四个分片，不是合成数据。Raw标定7、正式主服务24、Gate6，共37个fresh-server cell、11,640业务/22测量wave。主服务与Gate、Raw标定分别统计，不合并对照基线。

## 归档身份

- 原tar.gz：234,884,895 bytes；SHA256 `ce8a001e246f04012d56276232ad2b4acb706149dfde60d0155473e649320cfc`。
- 四分片按part000→003拼接，前三各67,108,864 bytes，末份33,558,303 bytes；逐片SHA见package_receipt_v1.json。
- 1,246 regular成员，清单SHA `464d3e31166a1228cede4a823aa0ce15693b147a13ee6da9686cf6d6d3b13944`，位于raw_member_inventory_v1.json。
- 两份原freeze的58个Root依赖及564份source snapshot均在原包。模型权重和runtime大目录不在此包，使用父完整SHA/实际size/mtime与环境回执标识，不暗示有权重重新分发。
- freeze、原始请求/实际Prompt与Output IDs、native/RPC、遥测、轨迹、评分/分析源码、失败及版本记录均包含或由原freeze引用。原先未执行的包选择器漏5Root已补，旧源与回执保留，实际包58/58。

完整tar只在本地.artifacts留存，不重复提交大于100MB的单文件。Git提交4parts及metadata，恢复可由已发布字节离线进行，不访问GPU/SSH。

## 安全恢复

在仓库根运行Python（本机实际独立复算已通过；CPU脚本使用标准库）。下列是给复核者的新目录示例，**当前已完成的恢复和复算无需再执行**；入口拒绝覆盖先前尝试。

```powershell
python -B scripts/tsc_revision_final_local_archive_v1.py --workspace . --package results/tsc_task_faithful_open_arrival_20261018/evidence_package_v1 --archive .artifacts/reproduction_final_v1.tar.gz --restore .artifacts/reproduction_final_v1 --output .artifacts/reproduction_records_v1/local_archive_verification_v1.json
```

入口逐片核bytes/SHA，拼接后核tar SHA与成员集合，拒绝绝对路径、路径跳出、链接和覆盖；逐成员恢复后再核SHA、58原Root及正式预公开freeze。不会只凭压缩文件存在就产生PASS。

## 从原始记录重新计算

归档恢复通过后，使用已发布的独立复算控制入口：

```powershell
python -B scripts/tsc_revision_final_local_recompute_v1.py --root .artifacts/reproduction_final_v1 --records .artifacts/reproduction_records_v1
```

该控制入口在原tar生成后编写，随最终Git独立发布；不为嵌入它重打包原始证据。它运行归档中**未改动的**冻结分析源码（SHA `ac65994e9770494b91583474b23119f5f4373b2f0e1d4e2ffa42f4bae8336864`），对30正式与7标定cell重新评分，并核实际IDs、时钟、费用、native与全部分母。输出写local_independent_formal_v1/calibration_v1新目录，保留原formal_analysis_v1/calibration_analysis_v1。

预注册来源敏感性脚本仍读取原归档目录；控制入口先证明其summary值与requests/paired_performance CSV等同刚完成的原raw重算，再未改源码执行敏感性，输入等价有明确断言。不把重新读取旧summary当作科学重算，也不改AST路径/统计参数。最后重新核验1,246原成员不变。

## 已完成的复核

Study根目录的local_archive_verification_v1.json及local_independent_recompute_v1.json是实际回执：

- 37cells/11,640业务从原始记录独立复算，0 GPU请求；
- 正式summary 6,891叶、标定934叶、敏感性135叶精确；没有实际使用浮点容差；
- 正式9份、标定4份CSV全部字节相同；summary JSON原字节仅CRLF/LF不同，LF归一后精确，不声称所有文件原字节相同；
- 重算后全部原成员SHA不变。

local_independent_*execution_v1.json和console记录真实运行/返回码。actual_client_queue_forensics_v1.json是额外事后CPU时序描述，使用真实到达/开始/提交偏移与2秒显存采样，不模拟新调度器或宣称因果修复。

正式结论、分母和局限见四份最终MD及Trust矩阵。最终commit/blob发布核验见Study/final_publication_receipt_v1.json；历史操作state保持原样，不为表示文档交付而回写测量状态。全部弱收益、零分参考、L0差异、length和失败均保留。后续不再为提高倍率追加GPU。
