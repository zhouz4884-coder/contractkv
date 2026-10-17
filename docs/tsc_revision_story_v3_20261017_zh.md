# ContractKV 第三版正文交付记录

日期：2026-10-17。以7月25日实际投稿的四项贡献为锚点，在12页整合稿基础上恢复服务治理、模板摊销和SLO/多租户证据。没有新GPU实验或算法、阈值调整。本轮先完成正文，未撰写正式Response Letter。

入口：[主文PDF](../Paper/revision_story_v3_20261017/contractkv_tsc_story_v3.pdf)；[补充材料](../Paper/revision_story_v3_20261017/contractkv_supplement.pdf)；[修改决策](../Paper/revision_story_v3_20261017/audit/story_v3_decisions_zh.md)；[实际位置索引](../Paper/revision_story_v3_20261017/audit/evidence_locations.csv)。

## 结果

- 主文12页、补充材料6页；Fig.1/2双栏，Fig.3–6单栏。
- 摘要、Introduction、贡献4、评估VI.B与Conclusion突出Service-Template Certificate及25倍调用/7.7倍未隐藏成本摊销；严格完整wall和自由生成结果保留。
- 四配置/五家族宽度与独立零slack成本补测并列；Mistral负值、p99、L0、失败成本适配及安全边界仍在正文/补充材料中。
- Fig.1强化namespace、授权/版本/epoch关系和whole-block截断；Fig.3独立展示历史RULER；Fig.4保留D1/D2治理代价与低调D0绝对基线，不使用21.5倍标题。
- Table S-I交付五家族prepared/serving顺序；S-II交付4695条segment位移及指标定义。S-III恢复10–80身份趋势；S-IV分开RULER的cold/fan-out；S-V明确执行时钟SLO；S-VI比较方法职责；门禁与四方法质量分布也正式交付。
- 依据原始审稿意见保留Fig.4(c)：R1反对近零D0造成的头条倍率，R3要求D1/D2对照及坏布局拒绝。D2相对D1的均值代价为0.044 req/s、3.0%，不声称认证使安全布局无条件更快。

## 边界与后续

未直接搬回旧图无法在同一时钟下闭合的部分“net SLO goodput”数字；改用可复算TTFT、明确命名的执行时钟统计，以及同栈/固定到达SLO证据。相关原值和审计记录保留。

位置索引由实际aux/PDF标签和源文件生成，给出PDF页码、章节/图表号与TeX源行；这些源行不是PDF印刷行号。正式Response Letter应在本轮正文确认后逐条撰写，不能复用旧定位。
