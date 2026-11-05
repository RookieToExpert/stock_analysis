"""评分规则：纯函数，不联网。阈值的含义见 docs/MODEL.md。"""
FINANCIAL = ("银行", "保险", "证券", "多元金融")


def _n(v):
    return v if isinstance(v, (int, float)) and v == v else None


def _tier(v, tiers):
    """tiers 从高到低：[(门槛, 分数), ...]；缺数据记 0 分。"""
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


def metrics(d):
    """d: years(新→旧,每项 rev/np/roe/gm/ocf/capex/invest/paid)、bs、mv、ttm_np、high36、price。"""
    y = d["years"][:5]
    full = len(y) == 5
    vals = lambda k: [r[k] for r in y if _n(r.get(k)) is not None]
    np_sum = sum(vals("np"))
    ocf, capex = vals("ocf"), vals("capex")
    mv, bs = _n(d.get("mv")), d.get("bs") or {}
    eq, ta = _n(bs.get("equity")), _n(bs.get("assets"))
    cash = (bs.get("cash") or 0) + (bs.get("trade_asset") or 0)
    debt = sum(bs.get(k) or 0 for k in ("short_loan", "long_loan", "bond", "due_1y"))
    rev0, rev4 = (_n(y[0].get("rev")), _n(y[4].get("rev"))) if full else (None, None)
    fcf_avg = (sum(ocf) - sum(capex)) / 5 if full and len(ocf) == 5 and len(capex) == 5 else None
    paid = vals("paid")
    last_paid = paid[0] if paid else None
    ttm = _n(d.get("ttm_np"))
    sustainable = None
    if mv and fcf_avg is not None and paid:
        # 可持续分红：五年平均实付，且不超过平均 FCF 和 TTM 利润
        caps = [sum(paid) / len(paid), max(fcf_avg, 0)]
        if ttm is not None:
            caps.append(max(ttm, 0))
        sustainable = min(caps) / mv * 100
    gms, roes = vals("gm"), vals("roe")
    return {
        "full": full,
        "roe_med": _median(roes) if roes else None,
        "roe_min": min(roes) if roes else None,
        "gm_range": max(gms) - min(gms) if len(gms) >= 2 else None,
        "ocf_np": sum(ocf) / np_sum if np_sum > 0 and ocf else None,
        "rev_cagr": ((rev0 / rev4) ** 0.25 - 1) * 100 if rev0 and rev4 and rev0 > 0 and rev4 > 0 else None,
        "ep": ttm / mv * 100 if ttm is not None and mv else None,
        "fcf_yield": fcf_avg / mv * 100 if fcf_avg is not None and mv else None,
        "sust_yield": sustainable,
        "paid_years": sum(1 for v in paid if v > 0),
        "payout": sum(paid) / np_sum * 100 if np_sum > 0 and paid else None,
        "invest_vs_paid": sum(vals("invest")) <= sum(paid) if paid else None,
        "debt_ratio": (_n(bs.get("liab")) or 0) / ta * 100 if ta else None,
        "net_cash": cash >= debt,
        "gw_ratio": (bs.get("goodwill") or 0) / eq * 100 if eq and eq > 0 else None,
        "cash_ratio": cash / ta * 100 if ta else None,
        "debt_assets": debt / ta * 100 if ta else None,
        "loss_3y": any((r.get("np") or 0) < 0 for r in y[:3]),
        "ttm_loss": ttm is not None and ttm < 0,
        "kf_yoy": _n(d.get("kf_yoy")),
        "gm_delta": _n(d.get("gm_delta")),
        "drawdown": (1 - d["price"] / d["high36"]) * 100 if _n(d.get("price")) and _n(d.get("high36")) else None,
    }


def vetoes(d, m):
    """自动排雷：命中任一条直接出局。"""
    out = []
    name = d.get("name") or ""
    if "ST" in name.upper() or "退" in name:
        out.append("ST/退市风险")
    if any(k in (d.get("industry") or "") for k in FINANCIAL):
        out.append("金融股需单独建模")
    if not m["full"]:
        out.append("年报不足5年")
    if m["loss_3y"] or m["ttm_loss"]:
        out.append("近3年或TTM亏损")
    if m["ocf_np"] is not None and m["ocf_np"] < 0.6:
        out.append("5年现金流/利润<0.6")
    if m["ocf_np"] is None and m["full"]:
        out.append("5年累计利润非正或无现金流数据")
    if m["gw_ratio"] is not None and m["gw_ratio"] > 30:
        out.append("商誉/净资产>30%")
    return out


def warnings(m):
    """不否决，但必须人工解释。"""
    out = []
    if (m["cash_ratio"] or 0) > 20 and (m["debt_assets"] or 0) > 20:
        out.append("存贷双高")
    return out


def recent_state(m):
    """历史分数看不到当下恶化，这里单独判断。"""
    out = []
    if m["kf_yoy"] is not None and m["kf_yoy"] <= -20:
        out.append(f"扣非利润同比{m['kf_yoy']:.0f}%")
    if m["gm_delta"] is not None and m["gm_delta"] <= -3:
        out.append(f"毛利率同比{m['gm_delta']:.1f}pp")
    if m["drawdown"] is not None and m["drawdown"] >= 30:
        out.append(f"较3年高点回撤{m['drawdown']:.0f}%")
    return out


def score(m):
    q = (_tier(m["roe_med"], [(15, 12), (12, 8), (8, 4)])
         + (4 if (m["roe_min"] or 0) >= 8 else 0)
         + (4 if m["gm_range"] is not None and m["gm_range"] <= 8 else 0)
         + _tier(m["ocf_np"], [(1, 7), (0.8, 4)])
         + (3 if (m["rev_cagr"] or 0) >= 8 else 0))
    v = (_tier(m["ep"], [(8, 12), (6, 8), (4, 4)])
         + _tier(m["fcf_yield"], [(6, 12), (4, 8), (2, 4)])
         + _tier(m["sust_yield"], [(4, 6), (2.5, 3)]))
    p = m["payout"]
    payout_pts = 0 if p is None else 7 if 30 <= p <= 100 else 3 if p >= 10 else 0
    r = ((8 if m["paid_years"] >= 5 else 0) + payout_pts
         + (5 if m["invest_vs_paid"] else 0))
    dr = m["debt_ratio"]
    s = ((0 if dr is None else 7 if dr <= 40 else 4 if dr <= 60 else 0)
         + (7 if m["net_cash"] else 0)
         + (6 if m["gw_ratio"] is not None and m["gw_ratio"] <= 10 else 0))
    return {"质量": q, "估值": v, "回报": r, "安全": s, "总分": q + v + r + s}


def grade(total, vetoed, state=(), warned=()):
    if vetoed:
        return "出局"
    if total < 60:
        return "放弃"
    if total < 75:
        return "观察"
    return "事件复核" if state or warned else "候选"
