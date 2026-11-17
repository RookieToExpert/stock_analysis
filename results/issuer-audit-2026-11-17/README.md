# 2026-11-17 发行人抽查与资格检查

固定样本来自当时已下载的 3625 份文件：财务 20 只（5 只已退市、15 只在市），ST 30 个变更。种子与名单见 sample.json。样本不是完整历史股票池抽样；ST 样本来自供应商已有变更，不能发现供应商完全漏记的事件，因此不能用作正式 20/30 门槛通过证明。

## 已核对的事实

20 只合并净利润与找到的发行人报告数值一致，其中刚泰仅核到更正稿，不证明供应商 pubDate 对应原始版本。19 只已找到对应当期原报告的数值（部分是报告转载），仍未验收全字段、实际分红实施和历史原始版本。详情与来源见 financial-review.json；不能把合并净利润直接与归母净利润比较。

部分 PDF 直连下载持续超时，已停止本次新建的 PDF 核验进程，改读网页解析的发行人原文；未改动股票下载进程。没有用后一年年报追溯列示的值冒充原始版本。

30 个 ST 标记变更：24 个实施/撤销日得到公告支持，6 个实际为摘牌或退市整理期。公告中有事后披露的回顾，故只用于核查，不自动写成历史可交易资格。

| 股票 | 标记变更日 | 结论 | 证据 |
|---|---|---|---|
| sz.000670 | 2022-08-22 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://static.cninfo.com.cn/finalpage/2023-04-28/1216660066.PDF) |
| sz.000976 | 2024-08-27 | terminal：2024-08-27摘牌，不是撤销ST恢复正常交易 | [来源](https://static.cninfo.com.cn/finalpage/2024-08-27/1220989424.PDF) |
| sh.600680 | 2019-05-24 | terminal：2019-05-23已摘牌，5月24日字段变0不能解释为撤销ST | [来源](https://www.sse.com.cn/services/information/delisting/c/4871404.pdf) |
| sh.600515 | 2021-02-19 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://static.cninfo.com.cn/finalpage/2021-11-01/1211448996.PDF) |
| sh.688022 | 2026-05-06 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://static.cninfo.com.cn/finalpage/2026-08-01/1225452077.PDF) |
| sz.002220 | 2019-05-28 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://disc.static.szse.cn/download/disc/disk02/finalpage/2019-05-27/8f832714-6129-436b-ba76-664af5d973f6.PDF) |
| sz.002423 | 2017-04-21 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://epaper.cs.com.cn/zgzqb/images/2017-04/20/B052/ZQBXP0520420C.pdf) |
| sz.002248 | 2018-04-16 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://epaper.cs.com.cn/zgzqb/html/2018-04/13/nw.D110000zgzqb_20180413_2-B056.htm?div=-1) |
| sh.600530 | 2024-06-21 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=10283811&stockid=600530) |
| sz.002502 | 2021-05-25 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://disc.static.szse.cn/download/disc/disk02/finalpage/2021-05-22/2fe3d657-5322-4ea5-9a71-c1b62cb12644.PDF) |
| sh.600896 | 2021-05-06 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://www.sse.com.cn/disclosure/announcement/listing/stock/c/c_20220620_85796493.shtml) |
| sz.002308 | 2024-07-09 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://disc.static.szse.cn/disc/disk03/finalpage/2024-07-05/4658dd68-8676-4445-a961-b79d8573c23d.PDF) |
| sh.600651 | 2021-04-16 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://static.cninfo.com.cn/finalpage/2021-04-15/1209688323.PDF) |
| sz.002417 | 2023-06-15 | terminal：2023-06-15进入退市整理期；不是恢复正常资格 | [来源](https://disc.static.szse.cn/disc/disk03/finalpage/2023-07-06/fd6bf1ae-c362-40c2-a243-d3c3e50adeb8.PDF) |
| sz.002547 | 2026-04-30 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://disc.static.szse.cn/disc/disk03/finalpage/2026-04-29/526179cb-24aa-4478-91c8-5d731b95bf20.PDF) |
| sh.600735 | 2025-09-30 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://static.cninfo.com.cn/finalpage/2025-09-27/1224685305.PDF) |
| sz.002211 | 2025-04-25 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=10949925&stockid=002211) |
| sh.600375 | 2024-04-01 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://paper.cnstock.com/html/2025-03/27/content_2041011.htm) |
| sh.600485 | 2019-04-30 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://www.sse.com.cn/disclosure/magin/announcement/ssereport/c/c_20190429_4794492.shtml) |
| sh.600260 | 2023-02-15 | terminal：2023-02-15摘牌，非撤销ST | [来源](https://www.citics.com/newsite/tzgg/ywgg/202302/t20230224_1175640.html) |
| sz.002513 | 2020-04-29 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://static.cninfo.com.cn/finalpage/2021-06-18/1210269243.PDF) |
| sh.600291 | 2022-05-17 | terminal：2022-05-17进入退市整理期，非恢复正常资格 | [来源](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/HKSCC/2022/cc_HKSCC_NOM_108_2022.pdf) |
| sh.600339 | 2016-04-19 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://static.cninfo.com.cn/finalpage/2016-09-26/1202725613.PDF) |
| sh.600423 | 2017-05-03 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://static.cninfo.com.cn/finalpage/2018-02-10/1204411845.PDF) |
| sh.600526 | 2019-04-22 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://epaper.cs.com.cn/zgzqb/html/2020-02/18/nw.D110000zgzqb_20200218_3-B017.htm) |
| sz.002118 | 2023-08-04 | terminal：2023-08-04摘牌，非撤销ST | [来源](https://epaper.cs.com.cn/zgzqb/html/2023-07/31/nw.D110000zgzqb_20230731_2-B003.htm) |
| sh.600696 | 2017-03-29 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/magin/announcement/ssereport/c/c_20170328_4259806.shtml) |
| sh.600425 | 2018-05-03 | matches：上交所2018撤销退市风险警示表列600425生效日20180503 | [来源](https://www.sse.com.cn/aboutus/publication/factbook/documents/c/10170563/files/9f33f39ecb1c4546a88ec88b81105434.pdf) |
| sz.002316 | 2023-04-17 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://paper.cnstock.com/html/2023-04/14/content_1748014.htm) |
| sh.603922 | 2026-04-30 | matches：公告所述实施/撤销日期与样本一致 | [来源](https://static.cninfo.com.cn/finalpage/2026-05-30/1225337423.PDF) |

## 程序修复与边界

资格检查对历史 ST=1 后的 ST=0 不再直接放行。需要 st_release_verification 的 source、effective_date、available_date 和 normal_listing 状态；证据必须在生效当日或之前公布。未核实则 unknown。未来 ST 记录不影响过去评价。此保护也会保守拦住尚未补证的真正摘帽股票，不能把 unknown 当作已剔除后再宣称全市场覆盖通过。

eligibility-after.json.gz 是只读重跑结果，2026-09-01：已知年龄/ST合格2467、其中年报缺失1009、资格未知2089。下载继续变化，因此与前次报告的数量差异不能全部归因本次规则。

## 仍未通过

正式策略回测继续禁止。缺完整股票池、缺原始版本证据、缺实际分红与财务附注验收，均保留为未完成，不以测试通过代替。财报抽查目前只完成净利润口径核对，不称整个财务门槛通过。
