# 2026 年 9 月调仓日的财报补证

北京时间 11 月 18 日 13:37 固定的 3,997 个证券文件中，9 月 1 日有 3,007 只股票通过上市年限、ST 和行业筛选。核对发行人披露后，年报输入完整的有 2,969 只。其余 38 只涉及 51 个公司年度，披露数据都能找到，但平均归母净资产为负，ROE 无法用于可比筛选。该调仓日另有 1,419 只股票尚缺证券文件。[逐项数值和原文页码](resolutions-2026-09-01.csv) · [保留为不可比的 51 条](remaining-2026-09-01.csv) · [计数和快照指纹](summary.json)

| 原清单中的问题 | 核对结果 |
| --- | --- |
| 3,033 个经营现金流 / 净利润比率空白 | 用披露的合并经营现金流净额补齐所需金额。保留正负号、金额单位和原比率的空值。 |
| 53 个平均 ROE 空白 | 2 个补入可比 ROE。51 个保存归母净利润、期初和期末归母权益以及带符号的算术结果，继续排除出可比 ROE 筛选。 |
| 14 个主营业务收入、4 个毛利率、3 个归母净利润占比、3 个总股数 | 已逐项补证。主营业务收入来自年报附注的主营业务栏，总股数按股数披露。 |
| 5 张缺整行的年表 | 核全现金流表、资产负债表或利润表中策略需要的每项输入。三七互娱 2022 年缺利润表一整行，该行的 5 个必需字段均已核实。 |
| 1 份新增摘帽公告 | 声迅股份 2026 年 5 月 20 日复牌并撤销退市风险警示。[深交所原文](https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-05-19/baf80594-70c5-49d7-bae9-60d15ff4b2d9.PDF) |

11:32 时的原清单有 1,269 家、3,086 条。这次同一批股票的补证结果是 3,035 条可用、51 条不可比。之后新到的 67 个文件增加了 19 家、29 个现金流缺项，29 个均已核实。[原清单](../pit-evidence-2026-11-18/st-followup/gaps-2026-09-01.csv) · [新增清单](additional-gaps-2026-09-01.csv)

原始公告及修订版各自按公开日生效，评价日当天公开的文件从下一天开始可用。比如新日恒力 2022 年经营现金流在 2023 年 4 月披露为 5,314.42 万元，2024 年 12 月更正为 −3,340.71 万元。两期披露之间的评价沿用最初金额。当前清单最终引用 3,306 份披露，各份保留 PDF 的 SHA-256、页码和原表片段。40 个公司年度的供应商净利润与所读披露版存在差异，明细保留双方读数和精度。这些现金流直接取自发行人披露。[净利润差异明细](provider-profit-differences.csv) · [公告清单](filings-latest.json.gz)

## 复核

从仓库根目录运行以下命令，以只读方式检查本地数据。以后新下载的文件也可以用这条命令复查。

```sh
python3 model/eligibility_audit.py ~/stock_analysis/data/pit --day 2026-09-01 --gaps-csv /tmp/stock-gaps.csv
```

重建这次 9 月 1 日的证据需要 Python 的 requests、系统的 pdftotext 以及两张清单对应的 PIT 原始文件。以下命令中的 PIT_DIR 指向保存这些文件的目录。重建结果写入独立目录。

```sh
repo_results=results/issuer-annual-2026-11-18
original=results/pit-evidence-2026-11-18/st-followup/gaps-2026-09-01.csv
cache=/tmp/issuer-annual-replay
python3 model/collect_gap_reports.py "$original" "$cache" --inventory "$repo_results/filings-latest.json.gz"
python3 model/reconcile_gap_reports.py "$cache" "$cache/manifest.json" --day 2026-09-01 \
  --pit-dir "$PIT_DIR" --gaps-csv "$original" "$repo_results/additional-gaps-2026-09-01.csv" \
  --inventory "$repo_results/filings-latest.json.gz"
python3 model/publish_annual_evidence.py "$cache/ledger-draft.json" "$cache/manifest.json" \
  "$cache/rebuilt" --day 2026-09-01
```
