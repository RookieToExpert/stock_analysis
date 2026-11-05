#!/usr/bin/env python3
"""用法：python3 model/score.py 002749 600519 ...  数据源：东方财富、腾讯行情，只读。"""
import json, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rules import MANUAL, action, blue_chip, grade, metrics, missing_fields, recent_state, score, state_unknown, vetoes, warnings

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://emweb.securities.eastmoney.com/"}
F10 = "https://datacenter.eastmoney.com/securities/api/data"


def get(url):
    # CDN 偶有不通的节点，短超时重试比长时间等待更快
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers=HDR)
            return json.load(OPENER.open(req, timeout=8))
        except Exception:
            if i == 4:
                raise
            time.sleep(1 + i)


def rows(url):
    return ((get(url).get("result") or {}).get("data")) or []


def dividends(code):
    """按除息年份汇总已实施的普通股现金分红，单位元。接口 9201 表示无记录。"""
    d = get("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_SHAREBONUS_DET&columns=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)&pageNumber=1&pageSize=60&sortTypes=-1"
            "&sortColumns=PLAN_NOTICE_DATE&source=WEB&client=WEB")
    if not d.get("success") and d.get("code") != 9201:
        raise ValueError(f"分红接口异常: {d.get('code')} {d.get('message')}")
    out = {}
    for x in (d.get("result") or {}).get("data") or []:
        ex, cash, shares = x.get("EX_DIVIDEND_DATE"), x.get("PRETAX_BONUS_RMB"), x.get("TOTAL_SHARES")
        if x.get("ASSIGN_PROGRESS") == "实施分配" and ex and cash and shares:
            out[ex[:4]] = out.get(ex[:4], 0) + cash / 10 * shares
    return out


def fetch(code, quote=None):
    sh = code.startswith("6")
    secu = f"{code}.{'SH' if sh else 'SZ'}"
    flt = f'(SECUCODE="{secu}")'.replace('"', "%22")
    tail = f"filter={flt}&p=1&ps=30&sr=-1&st=REPORT_DATE&source=HSF10&client=PC"
    main = rows(f"{F10}/v1/get?reportName=RPT_F10_FINANCE_MAINFINADATA&columns=ALL&filter={flt}"
                "&pageNumber=1&pageSize=30&sortTypes=-1&sortColumns=REPORT_DATE&source=HSF10&client=PC")
    cf = rows(f"{F10}/get?type=RPT_F10_FINANCE_GCASHFLOW&sty=APP_F10_GCASHFLOW&{tail}")
    bal = rows(f"{F10}/get?type=RPT_F10_FINANCE_GBALANCE&sty=F10_FINANCE_GBALANCE&{tail}")
    cfy = {r["REPORT_DATE"][:4]: r for r in cf if r["REPORT_DATE"][5:10] == "12-31"}
    div = dividends(code)
    years = []
    for r in main:
        if r["REPORT_DATE"][5:10] != "12-31":
            continue
        c = cfy.get(r["REPORT_DATE"][:4], {})
        years.append({"year": r["REPORT_DATE"][:4], "rev": r.get("TOTALOPERATEREVE"),
                      "np": r.get("PARENTNETPROFIT"), "np_all": c.get("NETPROFIT"), "roe": r.get("ROEJQ"), "gm": r.get("XSMLL"),
                      "ocf": c.get("NETCASH_OPERATE"), "capex": c.get("CONSTRUCT_LONG_ASSET"),
                      "invest": c.get("ACCEPT_INVEST_CASH") or 0, "paid": div.get(r["REPORT_DATE"][:4], 0)})
    # TTM 扣非 = 最新累计 + 上年全年 - 上年同期累计
    latest = main[0]
    ttm = latest.get("KCFJCXSYJLR")
    ly = str(int(latest["REPORT_DATE"][:4]) - 1)
    by = {r["REPORT_DATE"][:10]: r for r in main}
    prev = by.get(ly + latest["REPORT_DATE"][4:10])  # 上年同期
    if latest["REPORT_DATE"][5:10] != "12-31":
        a = by.get(f"{ly}-12-31")
        ttm = ttm + a["KCFJCXSYJLR"] - prev["KCFJCXSYJLR"] if a and prev and ttm is not None else None
    kf_yoy = gm_delta = None
    if prev:
        k0, k1 = latest.get("KCFJCXSYJLR"), prev.get("KCFJCXSYJLR")
        if k0 is not None and k1 and k1 > 0:
            kf_yoy = (k0 / k1 - 1) * 100
        if latest.get("XSMLL") is not None and prev.get("XSMLL") is not None:
            gm_delta = latest["XSMLL"] - prev["XSMLL"]
    b = bal[0] if bal else {}
    # 报表行存在时，借款和商誉的空值表示未列示；报表整行缺失时保持未知
    z = lambda k: (b.get(k) or 0) if b else None
    bs = {"equity": b.get("TOTAL_PARENT_EQUITY"), "assets": b.get("TOTAL_ASSETS"), "liab": b.get("TOTAL_LIABILITIES"),
          "cash": ((b.get("MONETARYFUNDS") or 0) + (b.get("TRADE_FINASSET_NOTFVTPL") or 0)) if b.get("MONETARYFUNDS") is not None else None,
          "debt": sum(z(k) for k in ("SHORT_LOAN", "LONG_LOAN", "BOND_PAYABLE", "NONCURRENT_LIAB_1YEAR")) if b else None,
          "goodwill": z("GOODWILL")}
    # 批量筛选时由全市场列表传入 quote，避免逐只请求行情接口
    q = quote or get(f"https://push2.eastmoney.com/api/qt/stock/get?secid={1 if sh else 0}.{code}"
                     "&fields=f43,f58,f116,f127")["data"]
    return {"code": code, "name": q.get("f58"), "industry": q.get("f127"), "price": q["f43"] / 100,
            "mv": q.get("f116"), "ttm_np": ttm, "kf_yoy": kf_yoy, "gm_delta": gm_delta, "bs": bs, "years": years, "high36": None}


def price_stats(code):
    """返回 (近36个月前复权最高价, 月收益年化波动率%)。"""
    d = get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={1 if code.startswith('6') else 0}.{code}"
            "&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55&klt=103&fqt=1&end=20500101&lmt=37")
    rows_ = [x.split(",") for x in (d.get("data") or {}).get("klines") or []]
    if len(rows_) < 13:
        return None, None
    closes = [float(x[2]) for x in rows_]
    rets = [b / a - 1 for a, b in zip(closes, closes[1:]) if a > 0]
    mean = sum(rets) / len(rets)
    vol = (sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5 * 12 ** 0.5 * 100
    return max(float(x[3]) for x in rows_[-36:]), vol


def evaluate(d):
    """fetch 结果 -> 输出记录。分数档、近期状态、人工项分开。"""
    m = metrics(d)
    v, s, miss = vetoes(d, m), score(m), missing_fields(d)
    if not v and not miss and s["总分"] >= 60 and d.get("high36") is None:
        d["high36"], d["vol"] = price_stats(d["code"])
        m = metrics(d)
    st, w, unk = recent_state(m), warnings(m), state_unknown(m)
    g = grade(s["总分"], v, miss)
    return {"code": d["code"], "name": d["name"], "industry": d["industry"], "price": d["price"], "mv": d["mv"], **s,
            "等级": g, "动作": action(g, st, w, unk), "蓝筹条件": blue_chip(d["mv"], m), "排雷": v, "缺数据": miss,
            "近期状态": st, "状态未知": unk, "人工警示": w, "人工核查": {k: "未查" for k in MANUAL}, "metrics": m}


def main(codes):
    out = []
    for c in codes:
        try:
            out.append(evaluate(fetch(c)))
        except Exception as e:
            out.append({"code": c, "error": repr(e)})
        time.sleep(0.5)
    return out


if __name__ == "__main__":
    res = main(sys.argv[1:])
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
