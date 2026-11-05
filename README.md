# stock_analysis

A 股长期投资的选股标准、评分脚本和投资记录。

- [选股标准](docs/MODEL.md)
- [策略规格](docs/STRATEGY_SPEC.md)
- [AI 使用规则](docs/AI_VALIDATION.md)
- [国光股份持仓记录](journal/002749-国光股份.md)
- 规则试跑结果：`results/sanity_2026-11-05.json`，这不是推荐名单

```bash
python3 model/score.py 002749 600519
python3 model/screen.py
python3 model/report.py results/<日期>-v0.3
cd model && python3 test_rules.py && python3 test_report.py
```

筛选脚本内部直连数据接口，不使用环境代理。

**验证通过前，分数只供研究，不能当作已证明能赚钱的买入信号。**

本仓库内容用于个人研究，不构成投资建议。
