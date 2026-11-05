#!/usr/bin/env python3
"""用法：python3 model/score.py 002749 600519 ...  数据源：东方财富、腾讯行情，只读。"""
import json, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rules import MANUAL, fiscal_dividends, recent_from_rows, action, blue_chip, grade, metrics, missing_fields, recent_state, score, state_unknown, vetoes, warnings

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://emweb.securities.eastmoney.com/"}
F10 = "https://datacenter.eastmoney.com/securities/api/data"


MAIN_FIELDS = ("REPORT_DATE", "NOTICE_DATE", "UPDATE_DATE", "TOTALOPERATEREVE", "PARENTNETPROFIT",
               "KCFJCXSYJLR", "ROEJQ", "XSMLL", "ROIC", "ZCFZL")
CF_FIELDS = ("REPORT_DATE", "NOTICE_DATE", "UPDATE_DATE", "NETPROFIT", "NETCASH_OPERATE", "CONSTRUCT_LONG_ASSET",
             "ACCEPT_INVEST_CASH", "ASSIGN_DIVIDEND_PORFIT", "SUBSIDIARY_PAY_DIVIDEND")
BS_FIELDS = ("REPORT_DATE", "NOTICE_DATE", "UPDATE_DATE", "TOTAL_ASSETS", "TOTAL_LIABILITIES", "TOTAL_PARENT_EQUITY",
             "MONETARYFUNDS", "TRADE_FINASSET_NOTFVTPL", "SHORT_LOAN", "LONG_LOAN", "BOND_PAYABLE",
             "NONCURRENT_LIAB_1YEAR", "GOODWILL", "OPINION_TYPE")


class SchemaError(ValueError):
    pass


def check_schema(rows, fields, label):
    """字段缺失说明接口变了，要明确失败，不能变成缺分。"""
    if rows:
        lost = [f for f in fields if f not in rows[0]]
        if lost:
            raise SchemaError(f"{label}缺字段: {lost}")


def pick(row, fields):
    return {k: row.get(k) for k in fields}


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


DIV_FIELDS = ("REPORT_DATE", "REPORT_TIME", "NOTICE_DATE", "IMPL_PLAN_PROFILE", "ASSIGN_PROGRESS", "EX_DIVIDEND_DATE",
              "PAY_CASH_DATE", "IS_UNASSIGN", "TOTAL_DIVIDEND", "TOTAL_DIVIDEND_A")


def dividend_rows(code):
    """官方财年分红记录。接口返回空表示没有任何记录，不等于确认零分红。"""
    secu = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"
    d = get(f"{F10}/v1/get?reportName=RPT_F10_DIVIDEND_MAIN&columns=ALL&filter=(SECUCODE=%22{secu}%22)"
            "&pageNumber=1&pageSize=120&sortTypes=-1&sortColumns=NOTICE_DATE&source=HSF10&client=PC")
    if not d.get("success") and d.get("code") != 9201:
        raise ValueError(f"分红接口异常: {d.get('code')} {d.get('message')}")
    rows = (d.get("result") or {}).get("data") or []
    check_schema(rows, DIV_FIELDS, "分红")
    return [pick(r, DIV_FIELDS) for r in rows]


def fetch(code, quote=None):
    sh = code.startswith("6")
    secu = f"{code}.{'SH' if sh else 'SZ'}"
    flt = f'(SECUCODE="{secu}")'.replace('"', "%22")
    tail = f"filter={flt}&p=1&ps=30&sr=-1&st=REPORT_DATE&source=HSF10&client=PC"
    main = rows(f"{F10}/v1/get?reportName=RPT_F10_FINANCE_MAINFINADATA&columns=ALL&filter={flt}"
                "&pageNumber=1&pageSize=30&sortTypes=-1&sortColumns=REPORT_DATE&source=HSF10&client=PC")
    cf = rows(f"{F10}/get?type=RPT_F10_FINANCE_GCASHFLOW&sty=APP_F10_GCASHFLOW&{tail}")
    bal = rows(f"{F10}/get?type=RPT_F10_FINANCE_GBALANCE&sty=F10_FINANCE_GBALANCE&{tail}")
    check_schema(main, MAIN_FIELDS, "主要指标")
    check_schema(cf, CF_FIELDS, "现金流量表")
    check_schema(bal, BS_FIELDS, "资产负债表")
    cfy = {r["REPORT_DATE"][:4]: r for r in cf if r["REPORT_DATE"][5:10] == "12-31"}
    div_rows = dividend_rows(code)
    fy = fiscal_dividends(div_rows)
    years = []
    for r in main:
        if r["REPORT_DATE"][5:10] != "12-31":
            continue
        c = cfy.get(r["REPORT_DATE"][:4], {})
        years.append({"year": r["REPORT_DATE"][:4], "rev": r.get("TOTALOPERATEREVE"),
                      "np": r.get("PARENTNETPROFIT"), "np_all": c.get("NETPROFIT"), "kf": r.get("KCFJCXSYJLR"),
                      "roic": r.get("ROIC"), "roe": r.get("ROEJQ"), "gm": r.get("XSMLL"),
                      "ocf": c.get("NETCASH_OPERATE"), "capex": c.get("CONSTRUCT_LONG_ASSET"),
                      "invest": c.get("ACCEPT_INVEST_CASH") or 0, **{k: fy.get(r["REPORT_DATE"][:4], {"paid": None, "status": "未知"})[v]
                         for k, v in (("paid", "paid"), ("paid_status", "status"))}})
    ttm, kf_yoy, gm_delta = recent_from_rows(main)
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
            "mv": q.get("f116"), "ttm_np": ttm, "kf_yoy": kf_yoy, "gm_delta": gm_delta, "bs": bs, "years": years,
            **dict(zip(("high36", "vol", "closes"), price_stats(code))),
            "source": {"main": [pick(r, MAIN_FIELDS) for r in main[:24]],
                       "cash_flow": [pick(r, CF_FIELDS) for r in cf if r["REPORT_DATE"][5:10] == "12-31"][:7],
                       "balance": [pick(r, BS_FIELDS) for r in bal[:1]], "dividends": div_rows}}


def price_stats(code):
    """返回 (近36个月前复权最高价, 月收益年化波动率%, 月收盘价)。"""
    d = get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={1 if code.startswith('6') else 0}.{code}"
            "&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55&klt=103&fqt=1&end=20500101&lmt=37")
    rows_ = [x.split(",") for x in (d.get("data") or {}).get("klines") or []]
    closes = [float(x[2]) for x in rows_]
    if len(rows_) < 13:
        return None, None, closes
    rets = [b / a - 1 for a, b in zip(closes, closes[1:]) if a > 0]
    mean = sum(rets) / len(rets)
    vol = (sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5 * 12 ** 0.5 * 100
    return max(float(x[3]) for x in rows_[-36:]), vol, closes


def evaluate(d):
    """fetch 结果 -> 输出记录。分数档、近期状态、人工项分开。"""
    m = metrics(d)
    v, s, miss = vetoes(d, m), score(m), missing_fields(d)
    st, w, unk = recent_state(m), warnings(m), state_unknown(m)
    g = grade(s["总分"], v, miss)
    return {"code": d["code"], "name": d["name"], "industry": d["industry"], "price": d["price"], "mv": d["mv"], **s,
            "等级": g, "数据状态": "待核查" if miss else "完整", "动作": action(g, st, w, unk), "蓝筹条件": blue_chip(d["mv"], m), "排雷": v, "缺数据": miss,
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
