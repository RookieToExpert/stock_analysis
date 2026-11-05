# stock_analysis

A 股长期投资的选股标准、评分脚本和投资记录。

- [选股标准](docs/MODEL.md)
- [国光股份持仓记录](journal/002749-国光股份.md)
- 规则试跑结果：`results/sanity_2026-11-05.json`，这不是推荐名单

```bash
python3 model/score.py 002749 600519
cd model && python3 test_rules.py
```

本仓库内容用于个人研究，不构成投资建议。
