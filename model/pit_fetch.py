#!/usr/bin/env python3
"""下载时点版原始数据：python3 model/pit_fetch.py --lib <目录> [--lib <目录>] [--limit N] [--shard i/n]

每只股票一个 JSON，已存在就跳过。只保存 Baostock 原始字段，不计算分数。
"""
import json, sys, time
from datetime import date
from pathlib import Path

args = sys.argv[1:]
for i, a in enumerate(args):
    if a == "--lib":
        sys.path.insert(0, args[i + 1])
import baostock as bs

OUT = Path(__file__).parent.parent / "data" / "pit"
START, END = "2016-01-01", date.today().isoformat()
FIRST_ANNUAL, LAST_YEAR, FIRST_QUARTER = 2012, 2026, 2016
TABLES = (("profit", bs.query_profit_data), ("cash", bs.query_cash_flow_data), ("balance", bs.query_balance_data), ("dupont", bs.query_dupont_data))


def rows(r):
    if r.error_code != "0":
        raise RuntimeError(f"{r.error_code} {r.error_msg}")
    out = []
    while r.next():
        out.append(dict(zip(r.fields, r.get_row_data())))
    return out


def eval_days():
    days = []
    for y in range(2017, date.today().year + 1):
        for m in (5, 9):
            ds = rows(bs.query_trade_dates(start_date=f"{y}-{m:02d}-01", end_date=f"{y}-{m:02d}-15"))
            open_days = [d["calendar_date"] for d in ds if d["is_trading_day"] == "1"]
            if open_days and open_days[0] <= date.today().isoformat():
                days.append(open_days[0])
    return days


def universe():
    f = OUT / "universe.json"
    if f.exists():
        return json.loads(f.read_text())
    res = {}
    for d in eval_days():
        xs = [x for x in rows(bs.query_all_stock(day=d)) if x["code"][3:6] in ("600", "601", "603", "605", "688", "000", "001", "002", "003", "300", "301")
              and not (x["code"].startswith("sz.399") or x["code"].startswith("sh.000"))]
        res[d] = [x["code"] for x in xs]
        print(d, len(xs), flush=True)
    f.write_text(json.dumps(res))
    return res


def one(code):
    d = {"code": code, "fetched": date.today().isoformat(), "basic": rows(bs.query_stock_basic(code=code)), "fin": {k: [] for k, _ in TABLES}, "dividend": []}
    for y in range(FIRST_ANNUAL, LAST_YEAR + 1):
        qs = [4] if y < FIRST_QUARTER else [1, 2, 4]
        for q in qs:
            for k, fn in TABLES:
                if k == "cash" and q != 4:
                    continue
                d["fin"][k] += rows(fn(code, year=y, quarter=q))
        d["dividend"] += rows(bs.query_dividend_data(code=code, year=str(y), yearType="report"))
    f = "date,open,high,low,close,preclose,volume,tradestatus,isST"
    d["daily"] = rows(bs.query_history_k_data_plus(code, f, start_date=START, end_date=END, frequency="d", adjustflag="3"))
    d["adjust"] = rows(bs.query_adjust_factor(code=code, start_date="2012-01-01", end_date=END))
    return d


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print(bs.login().error_msg, flush=True)
    codes = sorted({c for xs in universe().values() for c in xs})
    if "--shard" in args:
        i, n = map(int, args[args.index("--shard") + 1].split("/"))
        codes = codes[i::n]
    todo = [c for c in codes if not (OUT / f"{c}.json").exists()]
    if "--limit" in args:
        todo = todo[:int(args[args.index("--limit") + 1])]
    print("codes", len(codes), "todo", len(todo), flush=True)
    t0, bad = time.time(), 0
    for n, c in enumerate(todo, 1):
        try:
            d = one(c)
            tmp = OUT / f"{c}.tmp"
            tmp.write_text(json.dumps(d, ensure_ascii=False))
            tmp.rename(OUT / f"{c}.json")
            bad = 0
        except Exception as e:
            bad += 1
            print("fail", c, repr(e)[:120], flush=True)
            if bad >= 10:
                raise SystemExit("连续失败 10 只，停止")
            time.sleep(5)
            bs.login()
        if n % 20 == 0:
            print(n, "/", len(todo), round((time.time() - t0) / n, 1), "s/stock", flush=True)
    bs.logout()
    print("done", flush=True)


if __name__ == "__main__":
    main()
