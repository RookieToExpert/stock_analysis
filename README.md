# stock_analysis

A 股长期投资的选股标准、评分脚本和投资记录。

- [选股标准](docs/MODEL.md)
- [策略规格](docs/STRATEGY_SPEC.md)
- [时点版策略规格 v1.1](docs/STRATEGY_SPEC_V1_1.md)
- [AI 使用规则](docs/AI_VALIDATION.md)
- [巴菲特因子研究线](docs/BUFFETT_FACTOR.md)
- [数据字段说明](docs/DATA_DICTIONARY.md)
- [持仓记录模板](journal/TEMPLATE.md)
- [v0.3.2 独立抽查](docs/evidence/v0.3.2_spot_audit.md)
- [阅读清单](docs/READING.md)
- 最新名单和输入快照：[results/2026-11-05-v0.3.2](results/2026-11-05-v0.3.2/README.md)
- [国光股份持仓记录](journal/002749-国光股份.md)
- 规则试跑结果：`results/sanity_2026-11-05.json`，这不是推荐名单

```bash
python3 model/score.py 002749 600519
python3 model/screen.py
python3 model/report.py results/<结果目录>
python3 model/recompute.py results/<结果目录>
python3 model/buffett.py results/<结果目录>
cd model && python3 -m unittest
```

筛选脚本内部直连数据接口，不使用环境代理。

**禁止用已知结局向 AI 索取买入理由；历史验证必须只使用当时可知的信息。**

**验证通过前，分数只供研究，不能当作已证明能赚钱的买入信号。**

本仓库内容用于个人研究，不构成投资建议。

- [v0.3.3 修复范围与验收](docs/evidence/v0.3.3_repair.md)（codex 分支；未替换运行中的 main 下载任务）

- [总回报重建、历史数据审计与周期实验](results/data-audit-2026-11-16/README.md)（独立研究输出；未完成正式回测验收）

- [r8 最新修复验收](results/action-completion-2026-11-17/README.md)：固定 329 只异常全部重建通过；完整历史数据及正式回测仍有独立验收门槛。

- [按调仓日查财报缺项和摘帽公告](results/pit-evidence-2026-11-18/README.md)。包含查询命令、发行人公告和可下载的逐股 CSV。
- [20 个历史调仓日的财报与摘帽核对结果](results/issuer-annual-2026-11-18/incremental/README.md)。截至北京时间 11 月 18 日 16:16，已复核 4,056 个证券文件，逐项可查财报缺项原因和发行人公告。
