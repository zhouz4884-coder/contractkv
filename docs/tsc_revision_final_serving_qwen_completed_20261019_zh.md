# 新保真固定到达：Qwen三重复阶段结果

2026-10-19香港时间。Qwen两个冻结负载、Raw/Contract各三fresh-process，共12/12 cells已经完成。6组编译子集配对检查通过后，原supervisor自动启动Mistral/Llama共同负载阶段。**这不是整个五批/30正式单元完成报告。**

## 实际结果

每个负载各1080业务配对、972未来配对。原始三进程全部保留，wall倍率为pooled时钟比，范围是三次实际配对描述，不是来源总体CI。

| 负载 | 双SLO达标：Raw→Contract | pooled绝对Goodput req/s | pooled wall吞吐倍率 | 三次配对wall倍率范围 | compiled future | compiled ID/finish变化 |
|---|---:|---:|---:|---:|---:|---:|
| common | 761 → 764 /1080 | 0.126074002 → 0.126569282 | 0.999986× | 0.999975–0.999995× | 54/972 | 0 |
| high | 46 → 82 /1080 | 0.013177818 → 0.023277243 | 0.990905× | 0.984928–0.997444× | 54/972 | 0 |

共同负载绝对增量约0.000495req/s，不能说稳定加速；高点绝对增量约0.010099req/s，但Raw达标量小，倍率不单独作为强结果。高点三次wall都略慢于Raw。固定到达时，wall受offered窗口约束，不能拿它与旧closed-loop1.619×直接组成因果升级曲线。

两负载分别66个compiled业务/54个compiled future，均来自同一个HotpotQA doc90 query scope。所有实际已编译输出对Raw及其真实见证均未观察到ID/finish变化；它们不是132个独立新来源。每个负载native完整39、零命中27（每次13/9），未见完整驻留保证。

## 拒绝原因是可复现的，不改held-out规则

每个负载三次共54个scope-repeat决定：3PASS、24作用域证据不足、18候选token margin拒绝、9 Python语法拒绝。各重复分解均为1/8/6/3，没有按结果重新选档或改scope。

18个候选GPU拒绝来自同样6个条件的重复；对应candidate minima为负，约−11.313至−0.406。不能将其解释成.125阈值略高，只需小降即可保持top1；当前证据也不支持为了覆盖放松16词/非literal边界。经济门禁未成为本组最终拒绝原因，是否有独立价值仍由后续隔离ON/OFF回答。

## 全路由质量与Raw重复分开

- common：13次上升、5次下降，均L0；5个下降输出中3个在同位置的三个Raw控制中出现。Raw两两1080比较有16个ID/finish变化、7上升/9下降。
- high：14次上升、6次下降，均L0；6个下降输出中4个在同位置Raw控制中出现。Raw两两1080比较有22个ID/finish变化、15上升/7下降。

阈值为原>0.03报告标准，非在线容差。这些Raw控制相关，不能将7个已出现变体或4个未出现变体自动作因果判决，也不把全部L0现象统称模型噪声。全部实际输出IDs、finish、分数和位置均保留；最终主分析仍独立重算冻结scorer。

## 当前决策与尚未证实的解释

1. 当前证据支持资格内行为保持与真实有限命中；弱覆盖/净收益则是本组严格条件的实测限制，不因其不漂亮而停止冻结矩阵或换源。
2. 继续已启动的跨模型12cells与隔离Gate6cells，不重跑已完成Qwen，不增加有利load/SLO，不通过松margin或扩作用域追回旧数字。
3. 待核假说：旧development选择的L3在保真长输入上可能较激进；本组负margin说明重排实际影响预测，但没有证明L2会更好，不能据held-out条件改档。若将来重校准，需独立DEV、冻结选择与新验证，本轮不增这条研究线。
4. 待核假说：12,160-token获准prefix与后续Raw工作集竞争可能造成部分缺失命中。现有初始counter并非全驱逐时间线，不能逐案断言；既有驻留探针不能代替本组因果日志。本轮不临时加入pinning/新调度算法。
5. 若后续出现有效scope内可复现质量反例，必须先定位最小问题，不能仅将其转成文字限制。当前跨阶段编译ID/finish检查未发现此类反例。

## 可复核入口

- `results/tsc_task_faithful_open_arrival_20261018/qwen_stage_interim_summary_v1.json`：上述全部三重复点值、来源分解、Raw比较与输入SHA。
- `repeat2_projection_v1.json`、`repeat3_projection_v1.json`及对应small_metrics；首轮文件保持原名不覆盖。
- `formal/qwen_execution_state_v1.json`、`qwen_exit_v1.json`与`qwen_execution_feasibility_v1.json`：12完整、exit0、6组检查。
- `scripts/tsc_revision_final_qwen_stage_summary_v1.py`：本地读取实际只读投影的零GPU聚合，不替代最终30cell主分析、来源敏感性和独立原始归档复算。

三个模型完整结果、Gate真实调用/覆盖/尾成本、条件来源敏感性、原始证据包与最终MD回填仍未完成。当前保持原四项贡献的证据边界，不提前宣称普遍SLO收益或一般零退化。
