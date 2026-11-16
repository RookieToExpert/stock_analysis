#!/usr/bin/env python3
"""测试东方财富按报告期利润表是否保留当时公告的版本。

用法：python3 audit/em_restate_probe.py fetch   下载（串行，间隔 >=2 秒，异常即停，不重试）
      python3 audit/em_restate_probe.py compare 离线对比 data/pit 的 Baostock 数据
"""
import collections, glob, json, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "em_test"
URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
YEARS = (2017, 2020, 2022)
INTERVAL, MAX_REQUESTS, MAX_PAGES = 2.0, 45, 14
CN = timezone(timedelta(hours=8))


def request(year, page):
    p = {"sortColumns": "NOTICE_DATE,SECURITY_CODE", "sortTypes": "-1,-1", "pageSize": "500", "pageNumber": str(page),
         "reportName": "RPT_DMSK_FN_INCOME", "columns": "ALL",
         "filter": f"""(SECURITY_TYPE_CODE in ("058001001","058001008"))(TRADE_MARKET_CODE!="069001017")(REPORT_DATE='{year}-12-31')"""}
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(p), headers={"User-Agent": "Mozilla/5.0"})
    with op.open(req, timeout=20) as r:
        if r.status != 200:
            raise SystemExit(f"HTTP {r.status}，停止")
        x = json.loads(r.read().decode())
    res = x.get("result") or {}
    if not x.get("success") or not res.get("data"):
        raise SystemExit(f"异常返回，停止：{str(x)[:200]}")
    return res


def fetch():
    OUT.mkdir(parents=True, exist_ok=True)
    n, t0 = 0, time.time()
    for y in YEARS:
        f = OUT / f"income_{y}.json"
        if f.exists():
            raise SystemExit(f"{f} 已存在，不覆盖")
        rows, page, pages, count = [], 1, 1, None
        while page <= pages:
            if n >= MAX_REQUESTS:
                raise SystemExit("达到请求上限，停止")
            if n:
                time.sleep(INTERVAL)
            res = request(y, page)
            n += 1
            pages, count = res["pages"], res["count"]
            if pages > MAX_PAGES:
                raise SystemExit(f"页数 {pages} 超出预期，停止")
            rows += res["data"]
            page += 1
        codes = {r["SECURITY_CODE"] for r in rows}
        print(y, "count", count, "rows", len(rows), "unique", len(codes), "requests", n, "seconds", round(time.time() - t0), flush=True)
        if len(codes) != count:
            print("  警告：分页去重后数量不等于 count", flush=True)
        f.write_text(json.dumps({"source": "eastmoney RPT_DMSK_FN_INCOME", "fetched_at": datetime.now(CN).isoformat(), "rows": rows}, ensure_ascii=False))


def baostock(year):
    stat, out = f"{year}-12-31", {}
    for f in glob.glob(str(ROOT / "data/pit/s[hz].*.json")):
        d = json.load(open(f))
        p = [r for r in d["fin"]["profit"] if r["statDate"] == stat]
        u = [r for r in d["fin"]["dupont"] if r["statDate"] == stat]
        if not p or not u or not p[0]["netProfit"] or not u[0]["dupontPnitoni"]:
            continue
        b = d["basic"][0]
        out[d["code"][3:]] = {"name": b["code_name"], "delisted": bool(b["outDate"]), "pub": p[0]["pubDate"],
                              "parent": float(p[0]["netProfit"]) * float(u[0]["dupontPnitoni"])}
    return out


def compare():
    res = {}
    for y in YEARS:
        em = {r["SECURITY_CODE"]: r for r in json.load(open(OUT / f"income_{y}.json"))["rows"]}
        bs = baostock(y)
        c, big, miss = collections.Counter(), [], []
        for code, b in bs.items():
            r = em.get(code)
            if r is None or r.get("PARENT_NETPROFIT") is None:
                c["missing"] += 1
                c["missing_delisted"] += b["delisted"]
                miss.append((code, b["name"], b["delisted"]))
                continue
            v, nd = float(r["PARENT_NETPROFIT"]), r["NOTICE_DATE"][:10]
            rel = abs(v - b["parent"]) / max(abs(b["parent"]), 1.0)
            late, early = nd > b["pub"], nd < b["pub"]
            c["compared"] += 1
            c["date_late"] += late
            c["date_early"] += early
            c["diff>0.1%"] += rel > 0.001
            c["diff>1%"] += rel > 0.01
            c["diff>10%"] += rel > 0.1
            c["diff>0.1%_and_late"] += rel > 0.001 and late
            c["diff>0.1%_same_date"] += rel > 0.001 and not late
            c["sign_flip"] += v * b["parent"] < 0
            if rel > 0.001 or late or early:
                big.append({"code": code, "name": b["name"], "delisted": b["delisted"], "pub": b["pub"], "em_date": nd,
                            "baostock_parent": round(b["parent"]), "em_parent": v, "rel": round(rel, 4)})
        big.sort(key=lambda x: -x["rel"])
        res[y] = {"baostock": len(bs), "em_all": len(em), "counts": dict(c), "missing": miss, "changed": big}
        print(y, "Baostock", len(bs), "EM全市场", len(em), dict(c))
        for x in big[:8]:
            print("   ", x)
        print("    missing sample", miss[:8])
    (OUT / "compare.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"fetch": fetch, "compare": compare}[sys.argv[1]]()
