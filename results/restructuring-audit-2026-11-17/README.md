# 公司行动修复与固定样本复算（2026-11-17）

计算修订：`2026-11-17-r7`。仅独立 codex 工作目录改动，main 下载和定时任务未修改。

## 结果

- 原固定3510只样本中的329只补充审计股票：135只重建通过，194只拒绝；较r6新增23只通过、0只退步。合并原2844只通过记录后共2979只通过内部一致性，337只因上市/退市时间不满足完整窗口排除。
- 剩余194只：192只除权参考价未解释、万科1只因子行动缺失、德赛电池1只付费配股未建模。后两项及192只公告核验不是等待下载完成就能解决的问题。
- 全套203项测试通过，旧2881条输入复算 mismatch=0、no_input=0。
- `total_return_verified=false`，未认证全市场公告、未放行正式策略回测。这里的通过仅表示既定税前研究指数的输入一致性。

## 修复规则

1. 重整股份全部给债权人或投资人时，原持有人获得股份为0。公告明确的除权参考价和前收盘锚点单独用于校验，不能把重整转增误记为持有人免费送股。
2. 实际派发现金/股份与公告摊薄的虚拟除权参数分别保存；所有定向修正都核对原值，原值发生变化则拒绝。
3. 跨供应商仅在高精度值四舍五入至6位后与原值完全相等时统一精度；不扩大价格容差、不按价格反推分红。
4. 窗口起点当天的分红可锚定次日重复且完全相同的复权因子；起点已是除权后收盘，不再支付一次分红。
5. 德赛电池2023-12-08属于需要出资的配股，明确标记不支持，保留公告证据。

## 本次新增21项发行人公告事件

|股票|除权日|持有人每股现金|持有人送转股|来源|
|---|---|---:|---:|---|
|sh.600165|2025-12-11|0|0|[公告](https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=11686563&stockid=600165)|
|sh.600375|2024-12-26|0|0|[公告](https://finance.sina.com.cn/roll/2024-12-25/doc-ineaqxse8074682.shtml)|
|sh.600589|2023-12-29|0|0|[公告](https://finance.sina.com.cn/jjxw/2023-12-28/doc-imzznxhq4595728.shtml)|
|sh.600715|2024-12-16|0|0|[公告](https://epaper.cs.com.cn/zgzqb/html/2024-12/13/nw.D110000zgzqb_20241213_3-B061.htm)|
|sh.600519|2025-06-26|27.673|0|[公告](https://epaper.cs.com.cn/zgzqb/html/2025-06/20/nw.D110000zgzqb_20250620_3-B013.htm)|
|sh.600211|2026-09-15|1.146|0|[公告](https://static.cninfo.com.cn/finalpage/2026-09-07/1225550288.PDF)|
|sh.600256|2025-07-18|0.622|0|[公告](https://static.cninfo.com.cn/finalpage/2025-07-10/1224119436.PDF)|
|sh.600720|2024-06-13|0.3674|0|[公告](https://paper.cnstock.com/html/2024-06/04/content_1926541.htm)|
|sh.601898|2024-08-20|0.555|0|[公告](https://www.chinacoalenergy.com/cms_files/jcms1/web2/site/attach/0/5c706ac8437542fc8b925e9dc0c84260.pdf)|
|sh.603259|2025-05-21|1.33169|0|[公告](https://epaper.cs.com.cn/zgzqb/html/2025-05/15/nw.D110000zgzqb_20250515_6-B028.htm)|
|sz.002352|2024-11-07|1.4|0|[公告](https://finance.sina.com.cn/jjxw/2024-10-31/doc-incukuyf7317060.shtml)|
|sz.002352|2026-09-17|0.49|0|[公告](https://finance.sina.com.cn/jjxw/2026-09-09/doc-inirensh4070907.shtml)|
|sz.001283|2024-06-18|0.48|0|[公告](https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=10268068&stockid=001283)|
|sz.001211|2026-06-04|0|0.3946202|[公告](https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-05-28/cbaf35ae-7de5-43e5-b0de-780159d10669.PDF)|
|sh.688032|2024-06-19|3.6|0.49|[公告](https://epaper.cs.com.cn/zgzqb/html/2024-06/13/nw.D110000zgzqb_20240613_2-B054.htm)|
|sh.600382|2024-07-12|0.1828|0|[公告](https://epaper.stcn.com/att/202407/05/ZQ05B028-BB_eBook.pdf)|
|sh.600580|2025-06-27|0.15|0.2|[公告](https://epaper.cs.com.cn/zgzqb/html/2025-06/20/nw.D110000zgzqb_20250620_5-B061.htm)|
|sz.001283|2025-06-12|0.4799991|0|[公告](https://static.cninfo.com.cn/finalpage/2025-06-05/1223766361.PDF)|
|sh.688032|2025-06-19|3.2|0|[公告](https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=11178160&stockid=688032)|
|sh.600382|2026-05-25|0.213|0|[公告](https://epaper.stcn.com/pic/202605/19/ac3075c01468538d18fcfc2123e00549.pdf)|
|sz.001283|2026-05-26|0.38|0.3|[公告](https://static.cninfo.com.cn/finalpage/2026-05-19/1225312469.PDF)|

公告日期与参考参数完整保存在 `model/verified_actions.json`。重整锚点不能由供应商 preclose 倒推；本批全部21个事件已逐项检查，并对涉及的16只股票执行完整窗口回归。

## 复算证据

`replay.json` 包含每只结果、失败分类、原基线哈希、两个行动账本哈希和回归差异；新增通过股票的 `*-risk.json.gz` 保存计算输入。`sh/sz.CODE.json.gz` 为公告修复前的日线及补充事件，回归测试直接读取，避免未来数据变化掩盖错误。

```sh
python3 model/replay_risk_audit.py /home/ecs-user/stock_analysis/data/pit results/expanded-risk-2026-11-16/after.json.gz results/risk-failures-2026-11-17 /tmp/stock-risk-replay
python3 -m unittest discover -s model
python3 model/recompute.py results/2026-11-05-v0.3.2
```

复算先逐只比较本地文件与原基线哈希，变动即拒绝比较；全程离线，不启动Baostock会话。

## 尚未达到的验收

- 192只除权参考异常及万科未知因子仍需独立证据，禁止推测填值。
- 配股需预先定义认购资金、到账与交易限制模型；当前研究指数不支持。
- 随机财报审计只完成净利润口径，分红与附注、历史未重述版本、行业市值证据尚未完成。
- 下载完成后还需完整股票池覆盖验收；正式策略回测和周期保护样本外验证未放行。
