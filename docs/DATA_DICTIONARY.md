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
| `invest` | `ACCEPT_INVEST_CASH` | 吸收投资收到的现金 | 元；v0.3.3 空值为未知，不按零给分 |
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

## v0.3.3 补充

- `as_of`：北京时间当前评价日期，不能代替真实历史可用日。`model_version` 控制规则版本。
- 分红五年窗口与配套利润、融资口径见 MODEL.md 的 v0.3.3 一节；窗口不随某只公司的状态挑选年份。
- `quarter_kf`、`quarter_kf_prev`：本期/上年同期单季扣非；Q1 直接取累计，Q2/Q3/Q4 差分前一期累计。`quarter_known` 明确标记是否完整；`quarter_kf_yoy` 仅正基期计算。
- `profit_deterioration`：累计与单季的由盈转亏、亏损扩大说明；不会用 None 静默吞掉亏损扩大。
- `invest` 仍为合并吸收投资现金，混有少数股东投资，不能覆盖非现金稀释；当前评分是该代理量的比较，不是完整股东稀释统计。
- `cash` 含货币资金与指定金融资产字段，未扣受限资金；`debt` 新抓取包含短贷、长贷、债券、一年内到期非流动负债与非流动租赁负债，永续工具仍需人工核查。不把这些口径声称为可用净现金全貌。
- 复权算法尚未独立核验，当前回撤/波动率继续是旧前复权代理；不等同于全收益指标，也不等同区间最大回撤。不得只换 fqt=2 后继续与原始实时价格相除。

## 后续计算修复（2026-11-16，价格/资产负债子口径版本化）

新抓取快照保留 model_version=0.3.3，并通过 price_risk.version=monthly-proxy-1 和 balance_basis=debt-includes-noncurrent-lease-v1 记录子口径。旧快照不补造这些字段，保持原复算行为。

- `price_risk` 保存原始月线、来源 URL、截止日期、参照收盘日期、指标与未知原因。只用评价月之前连续 37 个月的收盘价算 36 个月收益波动；高点用其中最后 36 个月最高价，回撤用同一序列最后收盘价。当前未完成月始终排除，因此这不是盘中回撤。重复月、缺月、无效价格均未知。
- 仍使用 fqt=1，明确是前复权价格风险代理；不声称解决了全收益算法。新结果固定带人工核验提示，不把旧代理悄悄称作总回报。
- 新 `debt` 增加 `LEASE_LIAB`（非流动租赁负债），一年内到期部分已包含在 `NONCURRENT_LIAB_1YEAR`，不重复加租赁附注明细。字段不存在时报 SchemaError；字段存在而未列示沿用现有报表零值约定。
- 现金未扣受限资金、非现金稀释、永续工具分类均在新结果中输出人工警示。只有接口字段名不能证明受限现金可全量剔除，永续工具也不能机械一律加债务。

### 直连行情备用来源

price_risk.basis 可为 eastmoney-fqt1 或 tencent-qfq；两源都失败则为 None。只在整个序列可用且验证通过时采用，原始行、来源 URL、主源失败原因都入快照。始终显式禁用环境代理。两源的前复权算法尚未证明完全一致，指标仍是代理，不能视作可靠全收益或忽略人工核验。

## 可用现金／完整债务核验 v2

新 fetch 的 balance_basis=cash-debt-verification-v2。账面 cash 与 debt（含非流动租赁）仍展示，但 net_cash 默认未知，不给“现金≥有息负债”的7分，并进入人工补查。

人工核验结果可在输入快照追加 balance_verification：available_cash、complete_interest_debt、statement_date、available_date、source。必须与 bs.statement_date 同期、可用日不晚于评价日、来源非空；可用现金不能大于账面代理，完整债务不能小于已知债务，金额有限且非负。只有核对附注和分类后才能填写，不自动生成“已核验”。永续工具按实际条款归类，不能机械全部加或全部不加。

这修复了未核实口径却先加安全分的问题，但不等于全市场受限资金/永续工具数据已补齐。旧快照没有 v2 标记时保留旧得分。融资仍为合并吸收投资现金代理，非现金稀释保持未覆盖提示。


同一 v2 抓取口径下，“分红≥股权融资”的5分也要求 financing_verification。合并吸收投资现金不能证明没有非现金稀释，不再独自支持这5分。核验记录需母公司融资总额 parent_equity_financing、与分红窗口一致的 start_year/end_year、非未来 available_date、source，以及明确 complete/includes_noncash/excludes_minority 均为 true；金额来自发行与股本事件台账，不自动推算。缺记录则该项未知、0分、人工补查。原 invest 字段继续保留作原始代理和缺失诊断。

## 2026-11-16-r4 默认总回报输入（替代上述“只用代理”的当前行为）

`price_risk.status=reconstructed` 表示本地不复权日线、公司行动与独立交易日历通过一致性检查；basis 为 `gross-ex-date-close-reinvestment-v1`。drawdown 为截至上个完整月末的当前回撤，max_drawdown 为区间最大回撤，vol 为36个月收益的样本标准差年化。均使用同一税前再投资指数，非实际到账交易收益。完整日线、事件、补充事件、来源日历与文件哈希保存在 source。

`data_checks_passed=true` 不等于公告全量审计通过，后者 `total_return_verified=false` 仍保留。当前研究主名单要求重建成功；无法重建则保留价格代理和 reconstruction_failure，`risk_eligible=false`，不参与新主名单的波动率门槛计算。旧快照无该字段时维持旧排名。

本地来源由 STOCK_ANALYSIS_PIT_DIR 指定，默认仓库 data/pit，只读不联网Baostock。网络补充来源继续显式禁用代理。新输入/结果含 calculation_revision=2026-11-16-r4，筛选输出 manifest 校验同日期、同修订；不兼容旧目录续跑。证据与剩余门槛见 [本次验收](../results/default-pipeline-2026-11-16/README.md)。

## 2026-11-16-r5 重复因子及公告纠正

默认修订升为r5。对已知公司行动之后、前后复权累计因子均未变的重复记录，仅跳过其“缺事件”误报，仍校验逐日参考价。source新增 adjustments、redundant_adjustment_dates、verified_actions，以保存原始因子、忽略日期及公告纠正前记录。

model/verified_actions.json只容纳已核对发行人公告的精确纠正，按证券、除息日、预期旧金额、零送转及非未来可用日匹配，未知冲突不得覆盖。现有一项为600007的2024-06-24特别分红漏记；并非通用自动判定。融资核验available_date须不早于窗口结束年年底，完整有息负债须非负。详见 [扩大样本验收](../results/expanded-risk-2026-11-16/README.md)。
