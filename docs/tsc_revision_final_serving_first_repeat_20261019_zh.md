# 保真固定到达：Qwen首次重复的完整配对预览

2026-10-19香港时间。4个fresh-server单元全部完成，每个360业务、324future。**这是新六来源、单次重复，不是最终三重复结论或CI。** 后续正式重复按390ea831冻结方案自动接续，不以本结果改输入、候选、margin、scope、SLO或评分。

## 实际服务与质量

| 负载 | Raw→Contract完整wall s | wall吞吐倍率 | 双SLO达标数 | 绝对Goodput req/s：Raw→Contract | 编译future | compiled ID/finish变化 |
|---|---:|---:|---:|---:|---:|---:|
| common | 2008.481 → 2008.505 | 0.999988× | 261 → 259 /360 | 0.129948925 → 0.128951612 | 18/324 | 0 |
| high | 1161.978 → 1179.758 | 0.984928× | 8 → 27 /360 | 0.006884815 → 0.022886042 | 18/324 | 0 |

高负载Raw仅8个达标，必须优先看绝对数与绝对Goodput，不把由小基线放大的倍率单独作主结论。共同负载的wall主要受冻结到达窗口约束；两路径近似相同不是通过省略认证费用获得。高负载Contract wall略长，负结果保留。

- common：22编译业务，native完整13、零命中9；业务logical-new-prefill 3,552,952→3,396,360（−4.407%），认证另计。实际7 RPC，完整controller工作28.380s。全业务输出tokens 12224→12441；>0.03上升4、下降2，都在L0。
- high：22编译业务，native完整13、零命中9；业务logical-new-prefill 3,552,952→3,396,360（−4.407%），认证另计。实际7 RPC，完整controller工作28.421s。全业务输出tokens 12287→12499；>0.03上升6、下降2，都在L0。

全部22个编译业务（含18future）只来自HotpotQA doc90的一个query scope。两个负载重复同一来源，不当作两组独立泛化证据。其他来源仍Raw；L0下降没有删掉，也没有未经Raw重复对照归为“普通噪声”。

## 稀疏覆盖的实际准入分解

两个负载各18个scope决定，分解完全相同：1 PASS、8 observation_scope_has_no_declared_exact_reuse、6 candidate_token_margin_below_floor、3 Python语法拒绝。经济门禁没有成为本轮最终拒绝原因。

六个GPU候选拒绝的candidate min margin全为负，范围约−11.313至−0.406；不是把0.125略降一点就能保留top1行为的临界正margin。不能为了提高覆盖而放松它们。作用域拒绝中包含17/23/46等较长回答；缺证据不证明未来必然错误，但也不能据held-out回答重新设16-word边界。语法保护对声明chat补全协议仍保留，未取消以制造Repo覆盖。

Doc90获准前缀提交12,160 tokens，实际编译请求13完整命中、9零命中。它说明资格和此刻驻留不同；结合完整Prompt-ID审计，不能将所有零命中直接归为索引错误。当前初始metrics没有完整驱逐时间线，不宣称已逐案证明回收原因。既有三来源的驻留探针可以提供机制背景，不能代替本轮每案因果日志。

## 本轮决策与后续

1. 继续原冻结重复，不因单次弱收益重选来源、改margin、改变layout档位或新开有利负载。
2. 目前没有观察到已获准子集的ID/finish变化或拒绝新增发布的不变量错误；低覆盖/费用/驻留是性能限制，不能混同认证正确性缺陷。
3. 第一轮不能说明所有新来源都没有可用区间，也不能以compiled零事件宣布修复普遍成功。完整新矩阵、Gate ON/OFF、来源/进程不确定性与Raw重复完成后再作总判断。
4. 若后续出现有效scope内部可复现质量反例，则先归因并做必要最小修复；不提前将其当文字限制处理。

只读投影通过原Raw日志SHA核验，nice=19，两个读取约1.49/1.59s，新增GPU请求0，没有改变线上或原始数据。这些投影不是替代最终独立评分/全费用分析；最终仍运行冻结主分析和预登记条件来源敏感性。

证据：`results/tsc_task_faithful_open_arrival_20261018/first_repeat_projection_v1.json`、`first_repeat_small_metrics_v1.json`及对应4个cell的summary/completion/client-audit。入口：`scripts/tsc_revision_final_completed_pair_projection_v1.py`、`tsc_revision_final_completed_pair_metrics_v1.py`。
