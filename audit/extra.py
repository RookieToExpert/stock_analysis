#!/usr/bin/env python3
"""补充核验：毛利率和前复权月线。python3 audit/extra.py <快照目录> <公告文本目录>"""
import gzip, json, re, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from compare import flat, numbers

OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


AMT = re.compile(r"\d{1,3}(?:,\d{3})+\.\d{2}")


def candidates(s):
    """金额候选。附注编号可能粘在金额前，所以同时尝试去掉前 1～2 位。"""
    for m in AMT.finditer(s):
        raw = m.group()
        for cut in (0, 1, 2):
            x = raw[cut:].lstrip(",")
            if re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d{2}", x):
                yield float(x.replace(",", ""))


def operating_revenue(pages):
    """营业总收入含利息收入时，取其中的营业收入。"""
    for t in pages:
        m = re.search(r"其中[:：]营业收入(?:[七五六八]、\d{1,2})?(\d{1,3}(?:,\d{3})+\.\d{2})", flat(t))
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def find_cost(pages, rev, gm):
    """在“营业成本”标签后找能还原毛利率的金额。"""
    x = _find_cost(pages, rev, gm)
    alt = operating_revenue(pages)
    if not x and alt and alt != rev:
        x = _find_cost(pages, alt, gm)
    return x


def _find_cost(pages, rev, gm):
    want = rev * (1 - gm / 100)
    for i, t in enumerate(pages):
        s = flat(t)
        for m in re.finditer("营业成本", s):
            for x in candidates(s[m.end():m.end() + 110]):
                if abs(x - want) / want < 0.0002:
                    return x, i + 1
    return None


def events(d):
    """从分红记录解析已实施事件：(除息日, 每股现金, 送转比例)。"""
    out = {}
    for r in d["source"]["dividend_main"]:
        ex, plan = (r.get("EX_DIVIDEND_DATE") or "")[:10], r.get("IMPL_PLAN_PROFILE") or ""
        if r.get("ASSIGN_PROGRESS") != "实施方案" or not ex:
            continue
        cash = re.search(r"派([\d.]+)元", plan)
        rat = sum(float(x) for x in re.findall(r"[送转]([\d.]+)", plan))
        out[ex] = (float(cash.group(1)) / 10 if cash else 0, rat / 10)
    return sorted(out.items())


def sina_daily(code):
    p = ("sh" if code[0] == "6" else "sz") + code
    u = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={p}&scale=240&ma=no&datalen=1023"
    b = OP.open(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}), timeout=25).read()
    return json.loads(b)


def rebuilt(rows, ev):
    """未复权月末收盘按除权公式还原到当前口径。"""
    month = {}
    for r in rows:
        month[r["day"][:7]] = (r["day"], float(r["close"]))
    out = []
    for k in sorted(month):
        day, p = month[k]
        for ex, (cash, rat) in ev:
            if ex > day:
                p = (p - cash) / (1 + rat)
        out.append(p)
    return out


def main(path, txt):
    with gzip.open(path / "inputs.jsonl.gz", "rt", encoding="utf-8") as f:
        inputs = {d["code"]: d for d in map(json.loads, f)}
    sample = json.loads((path / "audit_sample.json").read_text())["sample"]
    gm, px = [], []
    for s in sample:
        c = s["code"]
        d = inputs[c]
        for r in d["years"][:5]:
            st, cost, pg, src = "无法验证", None, None, None
            for y in (int(r["year"]), int(r["year"]) + 1, int(r["year"]) + 2):
                if y > 2025:
                    continue
                x = find_cost(json.loads((txt / f"{c}_annual{y}.json").read_text()), r["rev"], r["gm"])
                if x:
                    cost, pg, src = x[0], x[1], y
                    st = "一致" if y == int(r["year"]) else "快照=后续年报调整后"
                    break
            gm.append({"name": s["name"], "year": r["year"], "snapshot": r["gm"], "cost": cost, "page": pg, "report": src, "status": st,
                       "calc": None if cost is None else round((1 - cost / r["rev"]) * 100, 4)})
        rows = sina_daily(c)
        re_ = rebuilt(rows, events(d))
        snap = d["closes"]
        n = min(len(re_), len(snap))
        pairs = list(zip(re_[-n:], snap[-n:]))
        err = [abs(a - b) for a, b in pairs]
        px.append({"name": s["name"], "months": n, "max_abs": round(max(err), 3), "mean_abs": round(sum(err) / n, 4), "max_pct": round(max(e / b * 100 for e, (a, b) in zip(err, pairs)), 2)})
        time.sleep(1)
    (path / "audit_extra.json").write_text(json.dumps({"gm": gm, "price": px}, ensure_ascii=False, indent=0))
    from collections import Counter
    print(Counter(x["status"] for x in gm))
    for x in gm:
        if x["status"] != "一致":
            print(x)
    for x in px:
        print(x)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
