# 4,056 个证券文件的财报和摘帽核对

北京时间 2026 年 11 月 18 日 16:16，在已核对的 3,997 个证券文件上新增 59 个，按同一套规则复核了 20 个调仓日。最新调仓日 2026 年 9 月 1 日共核对 3,168 条财报缺项，其中 3,116 条取得可用数值。其余 52 条涉及 39 家平均归母净资产为负的公司，ROE 保留为空。在通过上市年限、ST 和行业检查的 3,057 家中，3,018 家具备全部年报输入。该日的 5,212 家股票池里另有 1,364 家尚缺证券文件。[首批 3,115 条数值及公告页码](../resolutions-2026-09-01.csv) · [新增 53 条数值及公告页码](added-2026-09-01.csv)

20 个调仓日原有 33,363 条财报缺项，按实际披露日期补证后剩余 1,100 条，全部可逐项解释。780 条属于不可比指标，312 条涉及调仓日前尚未公开年报，8 条涉及发行人已公告无法按期披露。一个公司年度出现在多个调仓日时会重复计数。各期需要再查的财报字段和摘帽公告均为 0。[逐条原因和原文](remaining-all-dates.csv) · [逐期计数](per-evaluation.json) · [快照及计数口径](summary.json)

新增股票涉及 112 个公司年度。西安宝德 2018 年报摘要在第 2 页披露全年经营现金流净额 967,602,935.57 元，第 3 页披露的四个季度金额相加完全一致。新宁物流 2023 年平均归母净资产为负，披露中的净利润和期初、期末归母净资产均可核对，平均 ROE 保留为不可比。[西安宝德年报摘要](https://static.cninfo.com.cn/finalpage/2019-03-22/1205923732.PDF#page=2) · [新宁物流年报](https://static.cninfo.com.cn/finalpage/2024-04-29/1219870334.PDF#page=118)

| 新核实的摘帽股票 | 生效日 | 发行人公告 |
| --- | --- | --- |
| 赛为智能 300044 | 2022-06-10 | [撤销退市风险警示及其他风险警示](https://static.cninfo.com.cn/finalpage/2022-06-09/1213647997.PDF) |
| 豆神教育 300010 | 2024-06-13 | [撤销退市风险警示及其他风险警示](https://static.cninfo.com.cn/finalpage/2024-06-12/1220325286.PDF) |
| 新宁物流 300013 | 2025-05-06 | [撤销退市风险警示及其他风险警示](https://static.cninfo.com.cn/finalpage/2025-04-30/1223414193.PDF) |
| 传智教育 003032 | 2026-06-11 | [撤销退市风险警示](https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-06-10/f9b610ea-5a04-468b-9a53-35b67a9c5d8e.PDF) |

## 查看或复现

在仓库根目录运行下面的命令，导出的 CSV 可按股票代码筛选，链接直接指向适用的公告或报表页。省略日期可以查看全 20 期。

```sh
python3 model/eligibility_audit.py ~/stock_analysis/data/pit --day 2026-09-01 \
  --explain-csv /tmp/stock-gap-details.csv
```

要重建仓库当前版本的证据，先按首批说明重建 9 月及历史两份账本，再用以下命令加入新增 59 个文件。PIT_DIR 指向两批证券文件所在目录。增量检索截止日为 2026-09-01，筛选时仍逐调仓日判断可用日期。[首批重建命令](../historical/README.md) · [增量输入 SHA-256](snapshot-sha256.txt.gz) · [增量公告及 PDF 哈希](filings.json.gz)

```sh
part=results/issuer-annual-2026-11-18/incremental
cache=/tmp/issuer-annual-replay
python3 model/collect_gap_reports.py "$part/source-gaps.csv" "$cache/incremental" \
  --inventory "$part/filings.json.gz"
python3 model/reconcile_gap_reports.py "$cache/incremental" "$cache/incremental/manifest.json" \
  --day 2026-09-01 --pit-dir "$PIT_DIR" --gaps-csv "$part/source-gaps.csv" \
  --inventory "$part/filings.json.gz"
python3 model/publish_annual_evidence.py "$cache/ledger-draft.json" "$cache/manifest.json" \
  "$cache/rebuilt" --day 2026-09-01 --additional-ledger "$cache/historical/ledger-draft.json" \
  --additional-ledger "$cache/incremental/ledger-draft.json"
```
