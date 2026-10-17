# ContractKV Story V4 正文与排版版（2026-10-17）

保留 V3，完成 Fig.1 对象语义、成本口径分离、Manifest 信任边界与相关证据呈现。实验数据、规则和四项核心贡献不变；没有新 GPU 实验。

## 阅读入口

- [12 页主文](contractkv_tsc_story_v4.pdf)
- [8 页补充材料](contractkv_supplement.pdf)
- [本轮修改记录](audit/story_v4_decisions_zh.md)
- [V4a 证据溯源核查](audit/evidence_provenance_audit_zh.md)
- [实际 QA](audit/manuscript_QA.json)与[独立重建记录](audit/independent_reproduction.json)
- [最终证据位置](audit/evidence_locations.csv)：实际 PDF 页码、图表号及 TeX 源行；不是 PDF 印刷行号或 Response Letter。

主文第 12 页右栏实际预留四分之一页的作者简介区，暂为空白。正式作者文字/照片确认后替换 `sections/author_biographies.tex`，再检查分页。未编造作者资料。

## 优先核查的位置

Fig.1 位于第 2 页；新增协议 Table II 位于第 4 页。V3 原成本 Table II 现在为第 7 页 Table III，仅保留部署 cohort 的残余 slack 结果；独立零 slack 诊断成本在补表 S-XIII。

Manifest 信任边界在第 11 页 §VIII.B。补充第 7 页集中给出六来源×三模型结果（S-XVI）、九例注册 helper（S-XVII）与开放到达绝对 Goodput 增量区间（S-XVIII）。CPU helper 仍未接入 live endpoint，可信运营者的语义误声明仍会通过。区间从冻结记录恢复，未重新 bootstrap。

V4a 追加补表 S-XIX–S-XXII：分开报告五家族结构统计、同四开发来源输入对照、原 Table III 相同请求的 RPC 成本重算，以及实际客户端绑定检查。四配置原报告均值已复现，但 Llama 缺 33 次中间/失败 RPC 时长，亦有 controller 计时缺口，不能称为完整历史全成本复现。旧 Table I 的 85.0%/2.4% 仍未找到测量生成链，当前主结构表数值没有改动。

HMAC 检查位置已纠正为受信任服务客户端；绑定错误选择 raw。域证书中的 tenant 通配不承担终端用户身份认证，需由受信任应用执行授权和后端入口保护；未声称已部署公共鉴权代理。

Fig.1–2 双栏，Fig.3–6 单栏。图均为矢量 PDF/可编辑文字 SVG，并有 600-dpi PNG。Fig.2/3/4/6 与 V3 保持逐字节相同。

## 复现

在本目录执行，依赖见 `requirements.txt`，字体与 LaTeX 要求见英文 README。

```powershell
python -B scripts/restore_evidence.py
python -B scripts/restore_revision_audit.py
python -B scripts/restore_closure_tables.py
python -B scripts/plot_figures.py
python -B scripts/plot_architecture.py
python -B scripts/build.py
python -B scripts/qa.py
python -B scripts/locate_evidence.py
python -B scripts/reproduce.py --output ../../.artifacts/story_v4a_rebuild
python -B scripts/package.py ../../submission/ContractKV_story_v4a_20261017.zip
```

当前交付的 QA 以 `manuscript_QA.json` 和 `independent_reproduction.json` 为准。保留的 V7 数据文件用于未改动的历史图表证据，不代表本轮 QA。旧版本及其验证记录仍在原目录。

这是正文审阅包，Response Letter 按用户要求在正文确认后再写。

QA 的 PASS 表示输出和声明边界通过核对，不代表已找回缺失的原始测量。上一交付 ZIP 保留，新审计版单独使用 V4a 文件名。
