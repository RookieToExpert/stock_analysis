# 20 个调仓日的财报和摘帽核对

本页记录 13:37 的首批快照。16:16 又纳入 59 个证券文件。[4,056 个文件的最新结果](../incremental/README.md)

2026 年 11 月 18 日 13:37（北京时间）固定了 3,997 个已下载的证券文件，另保存一份调仓股票池。2017 年 5 月至 2026 年 9 月的 20 个调仓日共列出 32,671 条财报缺项。补证并按实际披露日重跑后，仍须排除 1,093 条，每条都有公告或报表页码。20 期的待核摘帽公告均为 0。同一个公司年度进入多个调仓日时会重复计数。[逐期计数](per-evaluation.json) · [修复前明细](before-all-dates.csv.gz) · [剩余逐项原因及公告](remaining-all-dates.csv)

| 为什么仍须排除 | 调仓日累计条数 | 怎么核对 |
| --- | ---: | --- |
| 平均归母净资产为负，平均 ROE 无法比较 | 758 | 打开年报中的归母净利润、期初和期末归母权益，算术值保存在证据中，筛选时跳过。 |
| 营业收入为零，毛利率没有分母 | 15 | 原文证实主营业务收入为零时可以记零，毛利率保留为空。 |
| 到调仓日还没有公开年报 | 312 | 78 个公司年度，每个年度涉及利润、现金流、资产负债和杜邦四组输入。原始披露日和公告链接见下方。 |
| 发行人已公告无法按期披露 | 8 | 玉龙股份 2024 年报和威创股份 2023 年报，在次年 5 月 6 日调仓时各有四组输入不可用。 |

其中 5 家的供应商记录把 2019 年报日期标成了 2020 年 4 月，发行人实际在 6 月或 7 月才披露。修正后，5 月 6 日将这 5 家的四组年报输入全部排除，生成 20 条整表记录。初始清单里的个别字段随之归入整表记录，前后计数使用各自核实后的口径。[73 个延期或同日披露的公司年度](late-annual-reports.csv) · [5 家日期纠正及延期公告](late-financial-fields.csv) · [4 份后来修订的年报首次披露证据](late-original-publications.json) · [玉龙、威创公告及归档](notices)

最新一期 2026 年 9 月 1 日共核对 3,115 条财报缺项，3,064 条取得可用数据，51 条属于 38 家平均归母净资产为负的公司。在已通过上市年限、ST 和行业检查的 3,007 家中，2,969 家具备该期需要的全部年报输入。该调仓日另有 1,419 家尚缺证券文件。[9 月逐项数值、页码及计算方法](../README.md)

## 哪一版年报可以用

需要按字段查表的清单涉及 1,945 家公司、5,925 个公司年度。其中 5,923 个公司年度取得了可用的发行人披露，最终用到 6,691 份年报正文、摘要及其修订版。另有 73 个当期尚未披露的公司年度单独核对了发布日期。[证据范围及计数](summary.json)

按证券代码和报告期找年报正文或摘要，核对报告封面、金额单位、合并口径及当年列。调仓日当天公布的数字从次日开始可用。遇到修订，按原版和修订版各自的公开日取值。旧版被撤回后，必须等到有证据的替代版本才能继续用。对于如今标记为「已取消」的文件，记录发行人确认原版公开的更正公告、同期存档的同一份 PDF、完整文本比对，或两份文件逐项相同的金额与页码。逐项比对只能确认列出的字段。[原版和替代版本证据](archived-editions.json)

有两家上市公司更换过证券代码。旧代码下的年报保留原发行代码，新代码的读取须满足对应变更公告与生效日期。竖排、扫描件和异常表格逐项保留原文、页码与 PDF 校验值。[证券代码沿革](code-changes.json) · [逐页人工复核记录](reviewed-rows.json) · [广誉远 2013 年修订报告第 8 页](63853320-page8.png)

## 查看自己的股票和公告

在 `stock_analysis-codex` 仓库根目录运行以下命令，打开生成的 CSV，按证券代码筛选。每行有调仓日、报告期、字段、中文原因和公告链接。链接中的 `#page=` 指向 PDF 页码。省略 `--day` 可以导出全 20 期。下载目录只参与读取。

```sh
python3 model/eligibility_audit.py ~/stock_analysis/data/pit --day 2026-09-01 \
  --explain-csv /tmp/stock-gap-details.csv
```

## 复现冻结快照

证券文件名、全部文件内容及股票池均保存了校验值。用快照对应的文件运行下面两条命令，可以核对输入是否和本次审计相同。[证券名单](snapshot-filenames.txt.gz) · [SHA-256 校验清单](snapshot-sha256.txt.gz)

```sh
snapshot_hashes="$PWD/results/issuer-annual-2026-11-18/historical/snapshot-sha256.txt.gz"
(cd "$PIT_DIR" && gzip -dc "$snapshot_hashes" | sha256sum --quiet --check)
```

重建财务证据时，先执行上一级说明中的 9 月清单采集与提取，再执行下面的历史部分。`source-gaps.csv` 中的 2026-09-01 是检索截止日，覆盖更早调仓日新涉及的公司年度。实际使用时仍按每个调仓日单独检查公开日期。两批原始公告清单都固定了 PDF 哈希。

```sh
history=results/issuer-annual-2026-11-18/historical
cache=/tmp/issuer-annual-replay
python3 model/collect_gap_reports.py "$history/source-gaps.csv" "$cache/historical" \
  --inventory "$history/filings.json.gz"
python3 model/reconcile_gap_reports.py "$cache/historical" "$cache/historical/manifest.json" \
  --day 2026-09-01 --pit-dir "$PIT_DIR" --gaps-csv "$history/source-gaps.csv" \
  --inventory "$history/filings.json.gz"
python3 model/publish_annual_evidence.py "$cache/ledger-draft.json" "$cache/manifest.json" \
  "$cache/rebuilt" --day 2026-09-01 --additional-ledger "$cache/historical/ledger-draft.json"
```

本次核对的是这批证券文件缺失的年报输入及摘帽公告。股票下载完成后，全市场覆盖率和正式回测仍须按完整股票池验收。[策略的数据验收条件](../../../docs/STRATEGY_SPEC_V1_1.md)
