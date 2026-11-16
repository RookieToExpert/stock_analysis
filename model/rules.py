"""评分规则：纯函数，不联网。阈值的含义见 docs/MODEL.md。

未知用 None，真实的 0 用 0。缺数据不得分，也不能进入“合格”。
"""
import math
from datetime import date

FINANCIAL = ("银行", "保险", "证券", "多元金融")
CORE_YEAR = ("rev", "np", "np_all", "kf", "roe", "gm", "ocf", "capex")
CORE_BS = ("assets", "liab", "equity", "cash", "debt", "goodwill")
MANUAL = ("审计意见", "立案/处罚", "质押", "减持", "资金占用/担保")
BLUE_MV = 200e8


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _tier(v, tiers):
    if v is None:
        return 0
    for limit, pts in tiers:
        if v >= limit:
            return pts
    return 0


def _median(xs):
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def recent_from_rows(rows):
    """由主要财务指标行（新→旧）计算 TTM 扣非、同比。上年同期缺失时返回 None，不做近似。"""
    if not rows:
        return None, None, None
    latest = rows[0]
    date = latest["REPORT_DATE"][:10]
    year, tail = int(date[:4]), date[4:]
    by = {r["REPORT_DATE"][:10]: r for r in rows}
    prev = by.get(f"{year - 1}{tail}")
    kf = _n(latest.get("KCFJCXSYJLR"))
    ttm = kf
    if tail != "-12-31":
        last_year = by.get(f"{year - 1}-12-31")
        a = _n(last_year.get("KCFJCXSYJLR")) if last_year else None
        b = _n(prev.get("KCFJCXSYJLR")) if prev else None
        ttm = kf + a - b if None not in (kf, a, b) else None
    kf_yoy = gm_delta = None
    if prev:
        k1 = _n(prev.get("KCFJCXSYJLR"))
        if kf is not None and k1 is not None and k1 > 0:
            kf_yoy = (kf / k1 - 1) * 100
        g0, g1 = _n(latest.get("XSMLL")), _n(prev.get("XSMLL"))
        if g0 is not None and g1 is not None:
            gm_delta = g0 - g1
    return ttm, kf_yoy, gm_delta


def fiscal_dividends(rows):
    """按所属财年整理分红。返回 {年份: {"paid": 金额或 None, "status": 状态}}。

    TOTAL_DIVIDEND 是财年合计，同一年多行会重复，不能相加。
    实施：有已实施现金方案；不分配：年报明确不分配且没有实施；
    待实施：有现金方案但未实施；未知：只有中期不分配或信息不全。
    """
    years = {}
    for r in rows:
        t = r.get("REPORT_TIME") or ""
        if len(t) >= 10:
            years.setdefault(t[:4], []).append(r)
    out = {}
    for y, xs in years.items():
        done = [x for x in xs if x.get("ASSIGN_PROGRESS") == "实施方案" and "派" in (x.get("IMPL_PLAN_PROFILE") or "")]
        plan = [x for x in xs if x.get("ASSIGN_PROGRESS") != "实施方案" and "派" in (x.get("IMPL_PLAN_PROFILE") or "")]
        annual = [x for x in xs if (x.get("REPORT_TIME") or "")[5:10] == "12-31"]
        only_shares = [x for x in xs if x.get("ASSIGN_PROGRESS") == "实施方案"]
        if done:
            total = max((_n(x.get("TOTAL_DIVIDEND")) or 0) for x in done)
            out[y] = {"paid": total if total > 0 else None, "status": "实施" if total > 0 else "未知"}
        elif plan:
            out[y] = {"paid": None, "status": "待实施"}
        elif annual and (only_shares or any(str(x.get("IS_UNASSIGN")) == "1" for x in annual)):
            out[y] = {"paid": 0, "status": "不分配"}
        else:
            out[y] = {"paid": None, "status": "未知"}
    return out


def clean_years(years):
    """取最新 5 个唯一且连续的年度；不足则返回实际连续部分。"""
    seen, out = set(), []
    for r in years:
        y = int(r["year"])
        if y in seen:
            continue
        if out and y != int(out[-1]["year"]) - 1:
            break
        seen.add(y)
        out.append(r)
        if len(out) == 5:
            break
    return out


def dividend_years(d):
    """固定窗口，不跳过零分红或未知年份。7月1日前止于前年，否则去年。"""
    if d.get("model_version") != "0.3.3":
        return clean_years(d.get("years") or [])
    from datetime import date
    day = date.fromisoformat(d["as_of"])
    end = day.year - (2 if day.month < 7 else 1)
    by = {int(x["year"]): x for x in d.get("years", [])}
    return [by.get(y, {"year": str(y)}) for y in range(end, end - 5, -1)]


def recent_details(rows):
    """累计/单季同时观察；非正基期不用百分比掩盖亏损扩大。"""
    by = {r["REPORT_DATE"][:10]: r for r in rows}
    if not by:
        return {"quarter_kf_yoy": None, "profit_deterioration": [], "quarter_known": False}
    day = max(by)
    year, tail = int(day[:4]), day[4:]
    value = lambda y, t: _n(by.get(f"{y}{t}", {}).get("KCFJCXSYJLR"))
    now, prev = value(year, tail), value(year - 1, tail)
    alerts = []
    def assess(a, b, label):
        if a is None or b is None:
            return None
        if b <= 0 and a < b:
            alerts.append(label + "亏损扩大")
        elif b > 0 and a < 0:
            alerts.append(label + "由盈转亏")
        return (a / b - 1) * 100 if b > 0 else None
    assess(now, prev, "累计扣非")
    preceding = {"-03-31": None, "-06-30": "-03-31", "-09-30": "-06-30", "-12-31": "-09-30"}
    if tail not in preceding:
        a = b = None
    elif preceding[tail] is None:
        a, b = now, prev
    else:
        n0, p0 = value(year, preceding[tail]), value(year - 1, preceding[tail])
        a = now - n0 if None not in (now, n0) else None
        b = prev - p0 if None not in (prev, p0) else None
    yoy = assess(a, b, "单季扣非")
    return {"quarter_kf_yoy": yoy, "profit_deterioration": alerts,
            "quarter_known": a is not None and b is not None,
            "quarter_kf": a, "quarter_kf_prev": b}


def missing_fields(d):
    """核心字段覆盖检查，返回缺失项；非空即数据不足。"""
    y = clean_years(d.get("years") or [])
    out = []
    if len(y) < 5:
        out.append(f"连续年报{len(y)}年")
    for k in CORE_YEAR:
        n = sum(1 for r in y if _n(r.get(k)) is None)
        if n:
            out.append(f"{k}缺{n}年")
    dy = dividend_years(d)
    for key in ("paid", "np", "invest"):
        n = sum(_n(x.get(key)) is None for x in dy)
        if n:
            out.append(f"分红窗口{key}缺{n}年")
    bs = d.get("bs") or {}
    out += [f"资产负债表缺{k}" for k in CORE_BS if _n(bs.get(k)) is None]
    for k, label in (("ttm_np", "TTM利润"), ("mv", "市值")):
        if _n(d.get(k)) is None:
            out.append(f"缺{label}")
    return out


def metrics(d):
    y = clean_years(d.get("years") or [])
    full = len(y) == 5
    vals = lambda k: [r[k] for r in y if _n(r.get(k)) is not None]
    complete = lambda *ks: full and all(_n(r.get(k)) is not None for r in y for k in ks)
    mv, ttm = _n(d.get("mv")), _n(d.get("ttm_np"))
    bs = d.get("bs") or {}
    assets, liab, eq = _n(bs.get("assets")), _n(bs.get("liab")), _n(bs.get("equity"))
    cash, debt, gw = _n(bs.get("cash")), _n(bs.get("debt")), _n(bs.get("goodwill"))
    # 新口径仅对有附注核验的可用现金/完整债务给净现金安全分。
    # 账面代理仍用于展示与存贷双高观察，不能代替附注核验。
    verified = d.get("balance_verification") or {}
    net_cash = cash >= debt if cash is not None and debt is not None else None
    if d.get("balance_basis") == "cash-debt-verification-v2":
        net_cash = None
        available = _n(verified.get("available_cash"))
        complete_debt = _n(verified.get("complete_interest_debt"))
        try:
            valid_dates = (date.fromisoformat(verified.get("statement_date", ""))
                           <= date.fromisoformat(verified.get("available_date", ""))
                           <= date.fromisoformat(d.get("as_of", "")))
        except (ValueError, TypeError):
            valid_dates = False
        if (valid_dates and isinstance(verified.get("source"), str) and verified["source"].strip()
                and verified.get("statement_date")
                and verified.get("statement_date") == bs.get("statement_date")
                and verified.get("available_date") and verified["available_date"] <= d.get("as_of", "")
                and available is not None and complete_debt is not None
                and cash is not None and debt is not None
                and 0 <= available <= cash and complete_debt >= max(0, debt)):
            net_cash = available >= complete_debt
    np5 = sum(r["np"] for r in y) if complete("np") else None
    np_all5 = sum(r["np_all"] for r in y) if complete("np_all") else None
    ocf5 = sum(r["ocf"] for r in y) if complete("ocf") else None
    fcf_avg = (ocf5 - sum(r["capex"] for r in y)) / 5 if complete("ocf", "capex") else None
    dy = dividend_years(d)
    dc = lambda key: len(dy) == 5 and all(_n(x.get(key)) is not None for x in dy)
    paid5 = sum(x["paid"] for x in dy) if dc("paid") else None
    div_np5 = sum(x["np"] for x in dy) if dc("np") else None
    financing = sum(x["invest"] for x in dy) if dc("invest") else None
    financing_verified = None
    if d.get("balance_basis") == "cash-debt-verification-v2":
        financing = None
        evidence = d.get("financing_verification") or {}
        amount = _n(evidence.get("parent_equity_financing"))
        try:
            available = (len(dy) == 5 and date(int(dy[0]["year"]), 12, 31)
                         <= date.fromisoformat(evidence.get("available_date", ""))
                         <= date.fromisoformat(d["as_of"]))
        except (ValueError, TypeError, KeyError):
            available = False
        if (available and amount is not None and amount >= 0 and evidence.get("complete") is True
                and evidence.get("includes_noncash") is True and evidence.get("excludes_minority") is True
                and isinstance(evidence.get("source"), str) and evidence["source"].strip()
                and evidence.get("start_year") == int(dy[-1]["year"])
                and evidence.get("end_year") == int(dy[0]["year"])):
            financing = amount
        financing_verified = financing is not None
    roes, gms = (vals("roe"), vals("gm"))
    sustainable = None
    if mv and fcf_avg is not None and paid5 is not None and ttm is not None:
        sustainable = max(min(paid5 / 5, fcf_avg, ttm), 0) / mv * 100
    rev0, rev4 = (_n(y[0].get("rev")), _n(y[4].get("rev"))) if full else (None, None)
    return {
        "full": full,
        "roe_med": _median(roes) if complete("roe") else None,
        "roe_min": min(roes) if complete("roe") else None,
        "gm_range": max(gms) - min(gms) if complete("gm") else None,
        "ocf_np": ocf5 / np_all5 if ocf5 is not None and np_all5 and np_all5 > 0 else None,
        "rev_cagr": ((rev0 / rev4) ** 0.25 - 1) * 100 if rev0 and rev4 and rev0 > 0 and rev4 > 0 else None,
        "ep": ttm / mv * 100 if ttm is not None and mv else None,
        "ep_norm": sum(r["kf"] for r in y) / 5 / mv * 100 if complete("kf") and mv else None,
        "fcf_yield": fcf_avg / mv * 100 if fcf_avg is not None and mv else None,
        "sust_yield": sustainable,
        "paid_years": sum(x["paid"] > 0 for x in dy) if dc("paid") else None,
        "payout": paid5 / div_np5 * 100 if paid5 is not None and div_np5 and div_np5 > 0 else None,
        "invest_vs_paid": financing <= paid5 if paid5 is not None and financing is not None else None,
        "debt_ratio": liab / assets * 100 if liab is not None and assets else None,
        "net_cash": net_cash,
        "gw_ratio": gw / eq * 100 if gw is not None and eq and eq > 0 else None,
        "cash_ratio": cash / assets * 100 if cash is not None and assets else None,
        "debt_assets": debt / assets * 100 if debt is not None and assets else None,
        "loss_3y": any((_n(r.get("np")) or 0) < 0 for r in y[:3]),
        "ttm_loss": ttm is not None and ttm < 0,
        "np5_nonpositive": np5 is not None and np5 <= 0,
        "kf_yoy": _n(d.get("kf_yoy")),
        "gm_delta": _n(d.get("gm_delta")),
        "drawdown": (d["price_risk"].get("drawdown") if "price_risk" in d else
                     (1 - d["price"] / d["high36"]) * 100 if _n(d.get("price")) and _n(d.get("high36")) else None),
        "vol": _n(d.get("vol")),
        **({k: d.get(k) for k in ("quarter_kf_yoy", "profit_deterioration", "quarter_known")}
           if "quarter_known" in d else {}),
        **({"cash_debt_verified": net_cash is not None, "financing_verified": financing_verified} if d.get("balance_basis") == "cash-debt-verification-v2" else {}),
    }


def vetoes(d, m):
    out = []
    name = d.get("name") or ""
    if any(k in name.upper() for k in ("ST", "PT")) or "退" in name:
        out.append("ST/退市风险")
    if any(k in (d.get("industry") or "") for k in FINANCIAL):
        out.append("金融股需单独建模")
    if m["loss_3y"] or m["ttm_loss"]:
        out.append("近3年或TTM亏损")
    if m["np5_nonpositive"]:
        out.append("5年累计利润非正")
    if m["ocf_np"] is not None and m["ocf_np"] < 0.6:
        out.append("5年现金流/利润<0.6")
    if m["gw_ratio"] is not None and m["gw_ratio"] > 30:
        out.append("商誉/净资产>30%")
    return out


def warnings(m):
    """人工警示：不等于基本面恶化，但必须解释。"""
    out = []
    if (m["cash_ratio"] or 0) > 20 and (m["debt_assets"] or 0) > 20:
        out.append("存贷双高")
    return out


def recent_state(m):
    """近期状态：只放基本面恶化和股价大跌。"""
    out = []
    out.extend(m.get("profit_deterioration") or [])
    if m.get("quarter_kf_yoy") is not None and m["quarter_kf_yoy"] <= -20:
        out.append(f"单季扣非同比{m['quarter_kf_yoy']:.0f}%")
    if m["kf_yoy"] is not None and m["kf_yoy"] <= -20:
        out.append(f"扣非利润同比{m['kf_yoy']:.0f}%")
    if m["gm_delta"] is not None and m["gm_delta"] <= -3:
        out.append(f"毛利率同比{m['gm_delta']:.1f}pp")
    if m["drawdown"] is not None and m["drawdown"] >= 30:
        out.append(f"较3年高点回撤{m['drawdown']:.0f}%")
    return out


def state_unknown(m):
    return [k for k, label in (("kf_yoy", "利润同比"), ("gm_delta", "毛利率同比"), ("drawdown", "回撤")) if m[k] is None] + (["quarter_kf"] if m.get("quarter_known") is False else []) + (["可用现金及完整债务"] if m.get("cash_debt_verified") is False else []) + (["母公司融资及非现金稀释"] if m.get("financing_verified") is False else [])


def score(m):
    q = (_tier(m["roe_med"], [(15, 12), (12, 8), (8, 4)])
         + (4 if m["roe_min"] is not None and m["roe_min"] >= 8 else 0)
         + (4 if m["gm_range"] is not None and m["gm_range"] <= 8 else 0)
         + _tier(m["ocf_np"], [(1, 7), (0.8, 4)])
         + (3 if m["rev_cagr"] is not None and m["rev_cagr"] >= 8 else 0))
    v = (_tier(m["ep"], [(8, 12), (6, 8), (4, 4)])
         + _tier(m["fcf_yield"], [(6, 12), (4, 8), (2, 4)])
         + _tier(m["sust_yield"], [(4, 6), (2.5, 3)]))
    p = m["payout"]
    payout_pts = 0 if p is None else 7 if 30 <= p <= 100 else 3 if p >= 10 else 0
    r = (8 if m["paid_years"] == 5 else 0) + payout_pts + (5 if m["invest_vs_paid"] else 0)
    dr = m["debt_ratio"]
    s = ((0 if dr is None else 7 if dr <= 40 else 4 if dr <= 60 else 0)
         + (7 if m["net_cash"] else 0)
         + (6 if m["gw_ratio"] is not None and m["gw_ratio"] <= 10 else 0))
    return {"质量": q, "估值": v, "回报": r, "安全": s, "总分": q + v + r + s}


def grade(total, vetoed, missing=()):
    """分数档，只回答基础质量；近期状态和人工警示单独输出。"""
    if vetoed:
        return "出局"
    if missing:
        return "数据不足"
    return "合格" if total >= 75 else "观察" if total >= 60 else "放弃"


def blue_chip(mv, m):
    """稳健分红蓝筹的硬条件；波动率在全池内比较，由筛选汇总时处理。"""
    return bool(mv and mv >= BLUE_MV and m["paid_years"] == 5
                and m["payout"] is not None and 30 <= m["payout"] <= 80)


def action(g, state, warned, unknown):
    if g != "合格":
        return "不操作"
    if state:
        return "事件复核"
    if unknown or warned:
        return "人工补查"
    return "人工排雷"
