"""评分规则：纯函数，不联网。阈值的含义见 docs/MODEL.md。

未知用 None，真实的 0 用 0。缺数据不得分，也不能进入“合格”。
"""
FINANCIAL = ("银行", "保险", "证券", "多元金融")
CORE_YEAR = ("rev", "np", "np_all", "roe", "gm", "ocf", "capex", "paid")
CORE_BS = ("assets", "liab", "equity", "cash", "debt", "goodwill")
MANUAL = ("审计意见", "立案/处罚", "质押", "减持", "资金占用/担保")
BLUE_MV = 200e8


def _n(v):
    return v if isinstance(v, (int, float)) and v == v else None


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
    np5 = sum(r["np"] for r in y) if complete("np") else None
    np_all5 = sum(r["np_all"] for r in y) if complete("np_all") else None
    ocf5 = sum(r["ocf"] for r in y) if complete("ocf") else None
    fcf_avg = (ocf5 - sum(r["capex"] for r in y)) / 5 if complete("ocf", "capex") else None
    paid5 = sum(r["paid"] for r in y) if complete("paid") else None
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
        "fcf_yield": fcf_avg / mv * 100 if fcf_avg is not None and mv else None,
        "sust_yield": sustainable,
        "paid_years": sum(1 for r in y if (_n(r.get("paid")) or 0) > 0) if complete("paid") else None,
        "payout": paid5 / np5 * 100 if paid5 is not None and np5 and np5 > 0 else None,
        "invest_vs_paid": sum(r.get("invest") or 0 for r in y) <= paid5 if paid5 is not None else None,
        "debt_ratio": liab / assets * 100 if liab is not None and assets else None,
        "net_cash": cash >= debt if cash is not None and debt is not None else None,
        "gw_ratio": gw / eq * 100 if gw is not None and eq and eq > 0 else None,
        "cash_ratio": cash / assets * 100 if cash is not None and assets else None,
        "debt_assets": debt / assets * 100 if debt is not None and assets else None,
        "loss_3y": any((_n(r.get("np")) or 0) < 0 for r in y[:3]),
        "ttm_loss": ttm is not None and ttm < 0,
        "np5_nonpositive": np5 is not None and np5 <= 0,
        "kf_yoy": _n(d.get("kf_yoy")),
        "gm_delta": _n(d.get("gm_delta")),
        "drawdown": (1 - d["price"] / d["high36"]) * 100 if _n(d.get("price")) and _n(d.get("high36")) else None,
        "vol": _n(d.get("vol")),
    }


def vetoes(d, m):
    out = []
    name = d.get("name") or ""
    if "ST" in name.upper() or "退" in name:
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
    if m["kf_yoy"] is not None and m["kf_yoy"] <= -20:
        out.append(f"扣非利润同比{m['kf_yoy']:.0f}%")
    if m["gm_delta"] is not None and m["gm_delta"] <= -3:
        out.append(f"毛利率同比{m['gm_delta']:.1f}pp")
    if m["drawdown"] is not None and m["drawdown"] >= 30:
        out.append(f"较3年高点回撤{m['drawdown']:.0f}%")
    return out


def state_unknown(m):
    return [k for k, label in (("kf_yoy", "利润同比"), ("gm_delta", "毛利率同比"), ("drawdown", "回撤")) if m[k] is None]


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
