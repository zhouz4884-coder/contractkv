# 保真固定到达服务：Raw-only baseline 标定

2026-10-18 14:40 UTC 后。4/4 个 baseline fresh-server 单元、480 次真实 Raw 业务已完成，原 supervisor285458/worker285459 正常退出0。这里尚无本轮正式 ContractKV 效果。实际参数在669898c公开核SHA后，14:44 UTC启动后续3个Raw profiles，supervisor301481/worker301486，尚未完成。

## 冻结规则推导的实际工作点

| 项目 | 结果 |
|---|---:|
| Qwen3-8B 单endpoint容量（两GPU各一个burst的中位数） | 0.313519676 req/s |
| Mistral-7B 单endpoint容量 | 0.198783460 req/s |
| Llama-3.1-8B 单endpoint容量 | 0.212263461 req/s |
| 正式共同到达率：0.9×三模型容量最小值 | 0.178905114 req/s |
| Qwen另一个工作点：1.05×Qwen容量 | 0.329195660 req/s |
| Raw推导readiness TTFT SLO | 11,700 ms |
| Raw推导平均TPOT SLO | 435 ms |

容量为120次业务/实际完整service wall，不含server启动；包含固定client主循环、评分/日志、等待及最终drain。两个endpoint分别测量，不能将不同窗口速率相加冒充共同窗口的双卡系统容量。Qwen两个baseline同时运行；Mistral/Llama各一GPU同时运行，peer条件入账。

TTFT标定不使用burst的累积上游排队：各模型先取 backend TTFT + controller-to-submit 的P95，再取三模型最大值，乘预注册1.25并向上取100ms。TPOT同样取各模型P95最大值，乘1.25向上取5ms。实际P95如下：

| 模型 | Raw请求 | intrinsic TTFT P95 ms | 平均TPOT P95 ms |
|---|---:|---:|---:|
| Qwen3-8B | 240 | 6,968.543 | 347.308 |
| Mistral-7B | 120 | 9,288.455 | 159.124 |
| Llama-3.1-8B | 120 | 6,499.415 | 216.425 |

这些SLO反映两张3090、长保真输入及原双请求wave实现的Raw基准，**不是500ms等通用交互SLA，也不与旧500ms goodput实验合并**。较高TPOT是实际流记录计算的结果，不为了提高或降低goodput临时更换阈值。主指标要求TTFT与平均TPOT同时达标；TTFT-only次级指标和完整E2E分布另列。

少token请求也出现较长first-to-last输出窗口：如Qwen HotpotQA约11个tokens的TPOT约350ms、Llama Repo约9个tokens约393ms。最高TPOT请求的输出窗口与同wave另一请求的**HTTP提交至首token窗口**存在可核对重叠，见`Raw_high_TPOT_overlap_audit_v1.json`；后者含队列与prefill，不是纯GPU prefill测量。当前没有完整逐token到达时间或kernel时间，尚不能定位一次长stall，也不能唯一归因于某一GPU调度机制。保留原执行器，不借此另起chunked-prefill算法或调窄SLO。正式分析按实际first/end、native scheduler和轻量采样继续区分排队与后端费用。

## 独立复算与实际trace身份

实际Linux导出 `derived_profile_plan_v1.json` SHA256：

`9d1a3efec44e0e8b6aa35f5d80fd0cdbf023a871d8672652f52a8c1136f5f823`

Windows从4份实际Raw原文（合计30,174,361 bytes，逐份SHA核验）独立重算：容量、各模型P95、SLO和正式负载数值全部相同；三个arrival的成员、seed、顺序与端点相同。

首次严格字节核对先遇到Windows CRLF，再遇到CPython3.13与3.10的归一化浮点sum/libm舍入差异。两个CPU失败视图及回执均保留，GPU没有重跑。输出换行适配后，arrival offset最大绝对差为 `3.410605131648481e-13` 秒，小于事后声明的1ns比对容差；其他推导字段精确相同。不能把该复算写成全部文件逐字节相同。**实际执行只读取已冻结Linux trace，Raw/Contract必须使用同一个原始SHA，不读取本地重生成版本。**

独立入口：`scripts/tsc_revision_final_raw_local_recompute_v1.py`；回执：`calibration/derived_local_independent_check_v1.json`。原推导算法source SHA不变，适配只涉及输出JSON换行；CPU差异不改变模型、输入或执行参数。

## 下一个有界步骤

先公开实际derived计划、3个arrival及小型完成回执并核远程SHA，再启动 `.4 / .7 / 1.05 × Cq` 的3个Qwen Raw profiles。前两个在两GPU并行，最后一个独立；全部120请求/单元。profile完成后才生成并公开24服务+6隔离Gate的actual formal freeze，之后执行，不根据Contract效果调整来源、工作点或SLO。
