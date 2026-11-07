#!/usr/bin/env python3
"""下载时点版原始数据：python3 model/pit_fetch.py --lib <目录> [--lib <目录>] [--limit N] [--probe]

每只股票一个 JSON，已存在就跳过。只保存 Baostock 原始字段，不计算分数。

请求限制由 pit_guard.py 执行：单进程、请求至少隔 1 秒、北京时间每天最多 4 万次。
收到 10001011 立即退出，并写 data/pit_state/blocked.json；标记存在时不会发出任何请求。
人工确认可以恢复后，才运行 --clear-block。

单次请求 60 秒没收完、连接断开或没有响应，都算网络错误：丢弃连接，等 5 分钟，只重新登录一次。
重新登录失败，或之后没存下一只股票就又出网络错误，进程停止，等人工决定。
"""
import json, re, sys, time
from datetime import date
from pathlib import Path

from pit_guard import BLACKLIST, Blocked, Guard, NetworkError, QuotaDone, Stop

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "pit"
STATE = ROOT / "data" / "pit_state"
START = "2016-01-01"
FIRST_ANNUAL, LAST_YEAR, FIRST_QUARTER = 2012, 2026, 2016
PRE_IPO_YEARS = 2
STOCK_RESERVE = 160
RECONNECT_WAIT = 300
PROBE_CODE = "sh.600000"

bs = None
guard = None


def load_client(argv):
    global bs
    for i, a in enumerate(argv):
        if a == "--lib":
            sys.path.insert(0, argv[i + 1])
    import baostock
    import baostock.util.socketutil as sock
    bs = baostock
    return sock


def tables():
    return (("profit", bs.query_profit_data), ("cash", bs.query_cash_flow_data), ("balance", bs.query_balance_data), ("dupont", bs.query_dupont_data))


def period_end(y, q):
    return f"{y}-" + {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]


def period_deadline(y, q):
    return {1: f"{y}-04-30", 2: f"{y}-08-31", 3: f"{y}-10-31", 4: f"{y + 1}-04-30"}[q]


def clean_date(s):
    return s if isinstance(s, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else ""


def plan(basic, today):
    """返回 (要查的报告期, 要查的分红年份, 跳过项)。

    上市前保留 PRE_IPO_YEARS 年：招股期报告可能在上市前已公告，上市后的评价日能用到。
    退市后的报告公告日一定晚于退市日，回测用不到。
    法定披露截止日未到的报告期不查，避免把披露到一半的数据存成定稿。
    日期缺失或格式不对时，不按该日期跳过。
    """
    b = basic[0] if basic else {}
    ipo, out = clean_date(b.get("ipoDate")), clean_date(b.get("outDate"))
    first = int(ipo[:4]) - PRE_IPO_YEARS if ipo else FIRST_ANNUAL
    periods, years, skipped = [], [], {"periods": [], "dividend_years": []}
    for y in range(FIRST_ANNUAL, LAST_YEAR + 1):
        for q in ([4] if y < FIRST_QUARTER else [1, 2, 4]):
            late = out and period_end(y, q) > out
            if y < first or late or period_deadline(y, q) >= today:
                skipped["periods"].append([y, q])
            else:
                periods.append((y, q))
        if y < first or (out and y > int(out[:4])) or y > int(today[:4]):
            skipped["dividend_years"].append(y)
        else:
            years.append(y)
    return periods, years, skipped


def check(r):
    if r.error_code == BLACKLIST:
        guard.block(r.error_msg)
    if r.error_code != "0":
        raise RuntimeError(f"{r.error_code} {r.error_msg}")


def rows(r):
    check(r)
    out = []
    while r.next():
        out.append(dict(zip(r.fields, r.get_row_data())))
    check(r)
    return out


def login():
    check(bs.login())


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
    today = guard.today()
    basic = rows(bs.query_stock_basic(code=code))
    periods, years, skipped = plan(basic, today)
    d = {"code": code, "fetched": today, "basic": basic, "fin": {k: [] for k, _ in tables()}, "dividend": [], "skipped": skipped}
    for y, q in periods:
        for k, fn in tables():
            if k == "cash" and q != 4:
                continue
            d["fin"][k] += rows(fn(code, year=y, quarter=q))
    for y in years:
        d["dividend"] += rows(bs.query_dividend_data(code=code, year=str(y), yearType="report"))
    f = "date,open,high,low,close,preclose,volume,tradestatus,isST"
    d["daily"] = rows(bs.query_history_k_data_plus(code, f, start_date=START, end_date=today, frequency="d", adjustflag="3"))
    d["adjust"] = rows(bs.query_adjust_factor(code=code, start_date="2012-01-01", end_date=today))
    return d


def reconnect(again):
    if again:
        raise Stop("重新登录后再次出现网络错误，停止，等人工决定")
    print("wait", RECONNECT_WAIT, "s then login once", flush=True)
    time.sleep(RECONNECT_WAIT)
    try:
        login()
    except (NetworkError, RuntimeError) as e:
        raise Stop(f"重新登录失败，停止，等人工决定：{e!r}")


def download(args):
    OUT.mkdir(parents=True, exist_ok=True)
    codes = sorted({c for xs in universe().values() for c in xs})
    todo = [c for c in codes if not (OUT / f"{c}.json").exists()]
    if "--limit" in args:
        todo = todo[:int(args[args.index("--limit") + 1])]
    print("codes", len(codes), "todo", len(todo), "used today", guard.used(), flush=True)
    t0, bad, net_failed = time.time(), 0, False
    for n, c in enumerate(todo, 1):
        if guard.remaining() < STOCK_RESERVE:
            raise QuotaDone(f"今日剩余 {guard.remaining()} 次，不足一只股票，停止")
        try:
            d = one(c)
            tmp = OUT / f"{c}.tmp"
            tmp.write_text(json.dumps(d, ensure_ascii=False))
            tmp.rename(OUT / f"{c}.json")
            bad, net_failed = 0, False
        except NetworkError as e:
            print("network fail", c, repr(e)[:120], flush=True)
            reconnect(net_failed)
            net_failed = True
        except Exception as e:
            bad += 1
            print("fail", c, repr(e)[:120], flush=True)
            if bad >= 10:
                raise Stop("连续失败 10 只，停止")
            time.sleep(5)
            try:
                login()
            except Exception as e:
                print("login fail", repr(e)[:120], flush=True)
        if n % 20 == 0:
            print(n, "/", len(todo), round((time.time() - t0) / n, 1), "s/stock", "used today", guard.used(), flush=True)
    print("done", flush=True)


def probe():
    print(rows(bs.query_stock_basic(code=PROBE_CODE)), flush=True)
    print("probe ok", flush=True)


def main(argv=None):
    global guard
    args = sys.argv[1:] if argv is None else argv
    if "--shard" in args:
        raise Stop("--shard 已移除：Baostock 不允许并发")
    guard = Guard(STATE)
    if "--clear-block" in args:
        guard.block_file.unlink(missing_ok=True)
        print("已清除黑名单标记，未发送请求")
        return
    guard.acquire()
    sock = load_client(args)
    guard.install(sock)
    try:
        login()
        probe() if "--probe" in args else download(args)
    except Blocked:
        raise
    except BaseException:
        logout()
        raise
    logout()


def logout():
    try:
        if not guard.block_file.exists():
            bs.logout()
    except (Exception, SystemExit) as e:
        print("logout skipped", repr(e)[:80], flush=True)


if __name__ == "__main__":
    main()
