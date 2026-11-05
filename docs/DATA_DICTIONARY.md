# 数据字段说明

数据来自东方财富公开接口。快照保存这些原始字段、公告日和更新时间，见各结果目录的 `inputs.jsonl.gz`。

| 模型字段 | 来源字段 | 含义 | 单位或口径 |
|---|---|---|---|
| `rev` | `TOTALOPERATEREVE` | 营业总收入 | 元，年报 |
| `np` | `PARENTNETPROFIT` | 归母净利润 | 元，年报 |
| `np_all` | 现金流量表 `NETPROFIT` | 合并净利润 | 元，年报 |
| `kf` | `KCFJCXSYJLR` | 扣非归母净利润 | 元，累计值 |
| `roe` | `ROEJQ` | 加权净资产收益率 | % |
| `roic` | `ROIC` | 投入资本回报率 | %，接口计算值 |
| `gm` | `XSMLL` | 销售毛利率 | % |
| `ocf` | `NETCASH_OPERATE` | 合并经营现金流净额 | 元 |
| `capex` | `CONSTRUCT_LONG_ASSET` | 购建长期资产支付的现金 | 元 |
| `invest` | `ACCEPT_INVEST_CASH` | 吸收投资收到的现金 | 元，空值按报表未列示 |
| `paid` | `RPT_F10_DIVIDEND_MAIN.TOTAL_DIVIDEND` | 所属财年现金分红总额 | 元，财年合计，不能逐行相加 |
| `mv` | 行情 `f20` | 总市值 | 元 |
| `high36` | 东方财富月 K 线 | 36 个月前复权最高价 | 元 |
| `vol` | 东方财富月 K 线 | 36 个月月收益年化波动率 | % |

## 不使用的字段

`ASSIGN_DIVIDEND_PORFIT` 只保存作审计，不用于分红指标。它包含利息和少数股东分红，证据见 [字段核对](evidence/field_audit_600900_2025.md)。

## 口径规则

- 现金流比率使用合并经营现金流和合并净利润。
- 分红率使用普通股分红和归母净利润。
- 分红状态分为实施、不分配、待实施、未知；待实施和未知不得分。
- 财务数据是接口当前值，可能已被后续年报追溯调整，见 [v0.3.2 抽查](evidence/v0.3.2_spot_audit.md)。
- `NOTICE_DATE` 是公告日，`UPDATE_DATE` 是接口数据更新时间。快照保存两者，但这不证明数据等于公告当时的原始版本。
- 接口缺少预期字段时脚本直接失败；字段存在但值为空时，按 `docs/MODEL.md` 处理。
