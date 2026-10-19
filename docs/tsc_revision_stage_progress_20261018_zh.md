# ContractKV 最终实证进度（2026-10-19收口版）

**GPU、原始证据与本地独立复算均完成；后续不再派发GPU。** 用户选择“停止剩余门禁实验，收口已有证据”到达前，原冻结Gate六单元已经自然完成；全部结果保留，未启动追加实验。

| 项目 | 实际完成 |
|---|---|
| 原TableIII全成本 | 24cells/12配对/4725future，525controller/453RPC；归档/独立复算完成 |
| 多类型机制+Manifest | 9cells/855正式业务，180候选/135Manifest；另63失败业务保留；归档/复算完成 |
| 256等预算 /真实Repo | 3cells/240自然终止；3cells/72真实Repo，均完成 |
| 新保真到达Raw标定 | 7/7、840业务，先标定后冻结负载/SLO |
| 新主服务 | 24/24、8640业务/4320配对/3888future，210compiled future零ID/finish变化 |
| Gate真实控制 | 6/6、2160业务，ON/OFF各21RPC/18失败/54compiled future，54决定相同，无观察筛除 |
| CPU布局/margin/PSTP/尾/队列 | 完成；不追加GPU、改阈值或模拟替代队列 |
| 新原始包 | 4parts、234884895bytes、1246成员/58Root；SHA ce8a001e246f04012d56276232ad2b4acb706149dfde60d0155473e649320cfc |
| 新原包独立复算 | 37cells/11640业务，所有summary叶值精确、13CSV字节相同，原1246成员重核不变 |
| 最终交付 | 四MD、Trust矩阵、完成验收和离线README；Git完成以final_publication_receipt_v1.json为准 |

既有保真闭环Qwen/Mistral/Llama完整wall1.619040/1.109072/1.070281×及0/1296 compiled future保持，仍是各自协议下的证据。新来源固定到达四组wall .999986/.990905/.999372/.999568×，Goodput绝对增量来源敏感性区间均跨零；M/L新获准QA参考Raw为0F1。不能把前者替代后者，也不能用后者推翻所有已测部署价值。

实验结果已允许收口；下一阶段是正文整合、图表/补充证据嵌入、信任边界/引用/版式，之后才写Response Letter。不要重启已结束worker/分析/打包，不回写旧操作状态，不对旧PID发信号，不再询问GPU选择。
