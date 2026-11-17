#!/usr/bin/env python3
"""用法：python3 model/score.py 002749 600519 ...  数据源：东方财富、腾讯行情，只读。"""
import json, sys, time, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from rules import recent_details
import score_v032
from price_risk import calculate as calculate_price_risk
from risk_pipeline import current_risk
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rules import MANUAL, fiscal_dividends, recent_from_rows, action, blue_chip, grade, metrics, missing_fields, recent_state, score, state_unknown, vetoes, warnings

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://emweb.securities.eastmoney.com/"}
F10 = "https://datacenter.eastmoney.com/securities/api/data"
CALCULATION_REVISION = "2026-11-17-r6"


MAIN_FIELDS = ("REPORT_DATE", "NOTICE_DATE", "UPDATE_DATE", "TOTALOPERATEREVE", "PARENTNETPROFIT",
               "KCFJCXSYJLR", "ROEJQ", "XSMLL", "ROIC", "ZCFZL")
CF_FIELDS = ("REPORT_DATE", "NOTICE_DATE", "UPDATE_DATE", "NETPROFIT", "NETCASH_OPERATE", "CONSTRUCT_LONG_ASSET",
             "ACCEPT_INVEST_CASH", "ASSIGN_DIVIDEND_PORFIT", "SUBSIDIARY_PAY_DIVIDEND")
BS_FIELDS = ("REPORT_DATE", "NOTICE_DATE", "UPDATE_DATE", "TOTAL_ASSETS", "TOTAL_LIABILITIES", "TOTAL_PARENT_EQUITY",
             "MONETARYFUNDS", "TRADE_FINASSET_NOTFVTPL", "SHORT_LOAN", "LONG_LOAN", "BOND_PAYABLE",
             "NONCURRENT_LIAB_1YEAR", "LEASE_LIAB", "GOODWILL", "OPINION_TYPE")


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


def get(url, attempts=5):
    # CDN 偶有不通的节点，短超时重试比长时间等待更快
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=HDR)
            return json.load(OPENER.open(req, timeout=8))
        except Exception:
            if i == attempts - 1:
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


def balance_metrics(b):
    if b and "LEASE_LIAB" not in b:
        raise SchemaError("资产负债表缺字段: LEASE_LIAB")
    # 报表行存在时，借款和商誉的空值表示未列示；报表整行缺失时保持未知
    z = lambda k: (b.get(k) or 0) if b else None
    return {"statement_date": (b.get("REPORT_DATE") or "")[:10], "equity": b.get("TOTAL_PARENT_EQUITY"), "assets": b.get("TOTAL_ASSETS"), "liab": b.get("TOTAL_LIABILITIES"),
          "cash": ((b.get("MONETARYFUNDS") or 0) + (b.get("TRADE_FINASSET_NOTFVTPL") or 0)) if b.get("MONETARYFUNDS") is not None else None,
          "debt": sum(z(k) for k in ("SHORT_LOAN", "LONG_LOAN", "BOND_PAYABLE", "NONCURRENT_LIAB_1YEAR", "LEASE_LIAB")) if b else None,
          "goodwill": z("GOODWILL")}


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
                      "invest": c.get("ACCEPT_INVEST_CASH"), **{k: fy.get(r["REPORT_DATE"][:4], {"paid": None, "status": "未知"})[v]
                         for k, v in (("paid", "paid"), ("paid_status", "status"))}})
    ttm, kf_yoy, gm_delta = recent_from_rows(main)
    b = bal[0] if bal else {}
    bs = balance_metrics(b)
    # 批量筛选时由全市场列表传入 quote，避免逐只请求行情接口
    q = quote or get(f"https://push2.eastmoney.com/api/qt/stock/get?secid={1 if sh else 0}.{code}"
                     "&fields=f43,f58,f116,f127")["data"]
    as_of = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    try:
        risk = current_risk(code, as_of, div_rows, get)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        risk = fetch_price_risk(code, as_of)
        risk["reconstruction_failure"] = f"{type(exc).__name__}: {exc}"
    return {"model_version": "0.3.3", "calculation_revision": CALCULATION_REVISION, "as_of": as_of,
            **recent_details(main), "code": code, "name": q.get("f58"), "industry": q.get("f127"), "price": q["f43"] / 100,
            "mv": q.get("f116"), "ttm_np": ttm, "kf_yoy": kf_yoy, "gm_delta": gm_delta, "bs": bs, "years": years,
            "balance_basis": "cash-debt-verification-v2",
            "price_risk": risk, **{k: risk[k] for k in ("high36", "vol", "closes")},
            "source": {"main": [pick(r, MAIN_FIELDS) for r in main[:24]],
                       "cash_flow": [pick(r, CF_FIELDS) for r in cf if r["REPORT_DATE"][5:10] == "12-31"][:7],
                       "balance": [pick(r, BS_FIELDS) for r in bal[:1]], "dividends": div_rows}}


def fetch_price_risk(code, as_of):
    """整条序列切换来源，不拼接。所有请求由无代理 OPENER 发出。"""
    market = 'sh' if code.startswith('6') else 'sz'
    primary = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={1 if market == 'sh' else 0}.{code}"
               f"&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55&klt=103&fqt=1&end={as_of.replace('-', '')}&lmt=38")
    fallback = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market}{code},month,,{as_of},40,qfq"
    failures = []
    for vendor, url in (("eastmoney-fqt1", primary), ("tencent-qfq", fallback)):
        raw = []
        try:
            response = get(url, attempts=2)
            if vendor == "eastmoney-fqt1":
                payload = response.get("data") or {}
                if payload.get("code") != code:
                    raise ValueError("unexpected security code")
                raw = payload.get("klines") or []
            else:
                if response.get("code") != 0:
                    raise ValueError("Tencent response error")
                payload = (response.get("data") or {}).get(market + code) or {}
                # 不接受 month/hfqmonth 代替明确要求的 qfqmonth。
                raw = [",".join(map(str, row[:5])) for row in payload.get("qfqmonth", [])]
            result = calculate_price_risk(raw, as_of)
            if result["status"] != "proxy":
                raise ValueError(result["reason"])
            result.update(basis=vendor, source_url=url, raw_klines=raw, source_failures=failures)
            return result
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            failures.append({"basis": vendor, "error": f"{type(exc).__name__}: {exc}",
                             "source_url": url, "raw_klines": raw})
    result = calculate_price_risk([], as_of)
    result.update(basis=None, reason="all price sources unavailable or invalid", source_failures=failures)
    return result


def evaluate(d):
    """fetch 结果 -> 输出记录。分数档、近期状态、人工项分开。"""
    if d.get("model_version") is None or d.get("model_version") == "0.3.2":
        return score_v032.evaluate(d)
    if d["model_version"] != "0.3.3":
        raise ValueError("Unsupported model_version")
    m = metrics(d)
    v, s, miss = vetoes(d, m), score(m), missing_fields(d)
    st, w, unk = recent_state(m), warnings(m), state_unknown(m)
    if "balance_basis" in d:
        if m.get("cash_debt_verified") is not True:
            w.append("可用现金、完整债务及永续工具需附注核验")
        if m.get("financing_verified") is not True:
            w.append("母公司融资及非现金稀释需事件台账核验")
    if "price_risk" in d:
        if d["price_risk"].get("status") == "reconstructed":
            w.append("总回报按除息日收盘再投资重建；全量发行人公告审计未完成")
        else:
            w.append("价格仅为代理：不参与新主名单波动率排名")
    g = grade(s["总分"], v, miss)
    return {"model_version": "0.3.3", "as_of": d["as_of"],
            **({"calculation_revision": d["calculation_revision"]} if "calculation_revision" in d else {}),
            **({"risk_eligible": d["price_risk"].get("status") == "reconstructed" and d["price_risk"].get("data_checks_passed") is True, "risk_basis": d["price_risk"].get("basis")} if "price_risk" in d else {}), "code": d["code"], "name": d["name"], "industry": d["industry"], "price": d["price"], "mv": d["mv"], **s,
            "等级": g, "数据状态": "待核查" if miss else "核心完整，专项待核查" if unk else "完整", "动作": action(g, st, w, unk), "蓝筹条件": blue_chip(d["mv"], m), "排雷": v, "缺数据": miss,
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
