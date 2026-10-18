# 最终保真服务桥梁：执行设计与有界标定

状态更新（2026-10-18 15:14 UTC）：新9源盲选及Raw-only7单元已完成，实际正式freeze `390ea8314f3e60f38c393c7b18873148f5e8d0af69bdeb6b89911cebe03652ff`与全部执行入口已生成，须预公开核SHA后才启动正式GPU矩阵。下文设计规则保持原值；不能把尚未完成的正式服务写成结果。原三批和7个Raw不再重做。

## 来源和方法固定

桥梁六源：HotpotQA doc90/doc131/doc187，以及RepoBench humannorm、UHGEval、spira-jira-migration-advanced。前四个保留完整原文，后两个按原packer仅裁可选context；CODE_PREFIX、问题和原始空白不裁。排除原704源及另3个Repo机制来源后选取，已知并集713。全部3模型×10租户×10轮的Raw/candidate形状有CPU hashes；正式服务用6租户子集。

使用原16K保真规则、现有query-qualified准入、128-token QA/384-token Repo预算、margin/EOS/语法/PSTP和原经济门禁。仅继承已有v5“不完整Raw见证返回L0、0RPC/0提交”异常修复。候选/floors不调。新固定到达wrapper显式绑定本地faithful renderer，修复旧adapter未覆盖fixed本地引用的问题。

## 服务时钟必须补上的实现检查

现fixed client在最后业务/注册返回后直接取service_end，再作日志audit。正式新入口需要**在service_end之前**明确等待backend running/waiting连续两次为0，保存drain时长；该等待计入Raw/Contract两条路径。只扩展最后计时边界，原到达、双请求barrier、规划、评分和注册循环不变。使用可审计的AST单点适配，不修改旧fixed原文件或旧5/54数据。

性能期间不安装重型residency hook。只用原initial metrics和轻量Prometheus（0.5秒采样）记录active/queue/KV usage/preemption，实际pool及物理prefix/new-prefill由native初始记录补齐。快照不是全程峰值，缺counter不填0，allocator-used不等于所有cached-resident。

## Raw-only有界标定：最多7个fresh-server cells、840次回答

每cell六来源、每来源2租户、每租户10轮=120请求，生成和输入规则同正式，先不产生任何Contract结果。

1. 两GPU同时各跑一个Qwen Raw burst（全部计划offset=0），得到两卡各自的实际N/full-wall容量估计。两server均ready再启动client。
2. Mistral/Llama各占一GPU同时跑Raw burst。得到各模型实际容量。
3. Qwen Raw三个负载profile：0.4、0.7、1.05倍Qwen容量；前两个并行、最后一个单独。只验证轻/中/近饱和区间和执行可行性，不根据Contract收益选点。

Qwen容量Cq取两个burst的中位数；Cm/Cl取各自burst值。正式共同负载`lambda_common=0.9*min(Cq,Cm,Cl)`，Qwen另一个近饱和点`lambda_high=1.05*Cq`。这些公式在Raw输出前确定；不因为某点倍率不好增添新的有利点。不同卡/同宿主并行条件均入账。

SLO从Raw burst的**自身wave开销**推导，不用burst累积队列当业务SLA：TTFT自身开销为backend TTFT + controller-to-submit。先按模型取P95，再取三模型最大值。TTFT SLO=该值×1.25向上取100ms，至少100ms；TPOT SLO=P95 TPOT最大值×1.25向上取5ms，至少20ms。主要Goodput要求两者同时满足；TTFT-only为预声明次级统计，E2E完整分布另报，不事后改SLO挑好结果。

## 正式到达与24个单元

每来源6租户×10轮，共360请求/180双请求waves。固定输入顺序，全部保留。wave间隔由固定seed的指数随机数产生，再统一缩放到预定总时长，使最后到达offset=`(waves-1)*2/lambda`，offered horizon=`N/lambda`。这是固定计数、归一化指数间隔的外生双请求wave轨迹，不冒称不受barrier限制的任意高并发Poisson服务。每个重复有独立seed；Raw/Contract同重复逐offset一致。

正式前将实际lambda、SLO、全部arrival文件、代码、模型/环境身份和统计方法一起冻结、公开。以**计划到达**计算queue、readiness TTFT/E2E；完整wall包括最后drain和计划idle。Goodput=满足SLO的全部业务数/full service wall；不只用compiled或future子集。

- Qwen先完成2负载×Raw/Contract×3重复=12cells。每wave两GPU分别承载共同/高负载，r2交换GPU。每个Raw/Contract配对保持同GPU、同peer负载；r2反转政策次序。两server均ready后启动两个client，等两个client均完成才停止server/加载下一wave，避免另一个cell加载模型干扰当前测量。
- Qwen执行与不变量可行后，Mistral/Llama共同负载各Raw/Contract×3，额外12cells。两模型同wave，Raw/Contract同GPU配对，r2交换GPU与政策次序。
- 每endpoint分别报告完整clock/吞吐/Goodput；不同结束时长的endpoint速率不能直接相加冒充共同窗口系统容量。

报告绝对Goodput、实际offered/achieved、Mean/P95/P99 TTFT/TPOT/E2E、实际IDs/分数双向变化、分来源/租户/请求路由、controller/RPC、native工作量、排队和资源约束。保持来源簇和进程重复两个层次，不能把租户当独立来源。

## Gate ON/OFF：独立隔离协议，最多6cells

使用同一事前冻结的六个独立来源、共同负载/到达、6租户10轮和相同SLO。ON/OFF各3个fresh-server，单GPU顺序配对（r2反序），另GPU不运行其他任务，以免把peer模型的CPU/IO干扰误算成门禁效果。这里的ON是**隔离运行条件**，不同于主矩阵的并行endpoint协议，因此不是无意义重跑已完成主结果，也不能直接借用主矩阵ON代替公平对照。

只关闭原经济decide分支，原scope、one_python_statement、margin/EOS和PSTP继续执行。原家族L0不越权。比较实际调用、失败/无复用认证、覆盖、完整wall、p99和绝对Goodput；没有隔离Raw基线，不借用并行Raw来声称隔离加速倍率。

这些是原五批目标所需的测量/消融，不增加新算法。边界固定为7个Raw标定、24个正式服务和6个Gate单元；不因表现温和继续扩展。基础设施失败独立记录、冻结修复、完整重跑受影响配对；科学负结果保留。若发现有效scope内部可复现行为失败，必须先归因，不能靠这份计划提前宣布修复完成。
