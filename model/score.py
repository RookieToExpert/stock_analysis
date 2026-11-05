#!/usr/bin/env python3
"""用法：python3 model/score.py 002749 600519 ...  数据源：东方财富、腾讯行情，只读。"""
import json, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rules import metrics, vetoes, warnings, recent_state, score, grade

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://emweb.securities.eastmoney.com/"}
F10 = "https://datacenter.eastmoney.com/securities/api/data"


def get(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers=HDR)
            return json.load(OPENER.open(req, timeout=20))
        except Exception:
            if i == 2:
                raise
            time.sleep(2)


def rows(url):
    return ((get(url).get("result") or {}).get("data")) or []


def fetch(code):
    sh = code.startswith("6")
    secu = f"{code}.{'SH' if sh else 'SZ'}"
    flt = f'(SECUCODE="{secu}")'.replace('"', "%22")
    tail = f"filter={flt}&p=1&ps=30&sr=-1&st=REPORT_DATE&source=HSF10&client=PC"
    main = rows(f"{F10}/v1/get?reportName=RPT_F10_FINANCE_MAINFINADATA&columns=ALL&filter={flt}"
                "&pageNumber=1&pageSize=30&sortTypes=-1&sortColumns=REPORT_DATE&source=HSF10&client=PC")
    cf = rows(f"{F10}/get?type=RPT_F10_FINANCE_GCASHFLOW&sty=APP_F10_GCASHFLOW&{tail}")
    bal = rows(f"{F10}/get?type=RPT_F10_FINANCE_GBALANCE&sty=F10_FINANCE_GBALANCE&{tail}")
    cfy = {r["REPORT_DATE"][:4]: r for r in cf if r["REPORT_DATE"][5:10] == "12-31"}
    years = []
    for r in main:
        if r["REPORT_DATE"][5:10] != "12-31":
            continue
        c = cfy.get(r["REPORT_DATE"][:4], {})
        years.append({"year": r["REPORT_DATE"][:4], "rev": r.get("TOTALOPERATEREVE"),
                      "np": r.get("PARENTNETPROFIT"), "roe": r.get("ROEJQ"), "gm": r.get("XSMLL"),
                      "ocf": c.get("NETCASH_OPERATE"), "capex": c.get("CONSTRUCT_LONG_ASSET"),
                      "invest": c.get("ACCEPT_INVEST_CASH") or 0, "paid": c.get("ASSIGN_DIVIDEND_PORFIT")})
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
    bs = {"equity": b.get("TOTAL_PARENT_EQUITY"), "assets": b.get("TOTAL_ASSETS"), "liab": b.get("TOTAL_LIABILITIES"),
          "cash": b.get("MONETARYFUNDS"), "trade_asset": b.get("TRADE_FINASSET_NOTFVTPL"),
          "short_loan": b.get("SHORT_LOAN"), "long_loan": b.get("LONG_LOAN"), "bond": b.get("BOND_PAYABLE"),
          "due_1y": b.get("NONCURRENT_LIAB_1YEAR"), "goodwill": b.get("GOODWILL")}
    q = get(f"https://push2.eastmoney.com/api/qt/stock/get?secid={1 if sh else 0}.{code}"
            "&fields=f43,f58,f116,f127")["data"]
    pfx = "sh" if sh else "sz"
    k = get(f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx}{code},month,,,36,qfq")
    months = k["data"][pfx + code].get("qfqmonth") or []
    return {"code": code, "name": q.get("f58"), "industry": q.get("f127"), "price": q["f43"] / 100,
            "mv": q.get("f116"), "ttm_np": ttm, "kf_yoy": kf_yoy, "gm_delta": gm_delta, "bs": bs, "years": years,
            "high36": max((float(x[3]) for x in months), default=None)}


def main(codes):
    out = []
    for c in codes:
        try:
            d = fetch(c)
            m = metrics(d)
            v = vetoes(d, m)
            w, st = warnings(m), recent_state(m)
            s = score(m)
            out.append({"code": c, "name": d["name"], "price": d["price"], "industry": d["industry"], **s,
                        "等级": grade(s["总分"], v, st, w), "排雷": v, "警示": w, "近期状态": st, "metrics": m})
        except Exception as e:
            out.append({"code": c, "error": repr(e)})
        time.sleep(0.5)
    return out


if __name__ == "__main__":
    res = main(sys.argv[1:])
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
