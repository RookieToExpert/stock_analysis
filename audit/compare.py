#!/usr/bin/env python3
"""把官方公告文本和快照逐项对比：python3 audit/compare.py <快照目录> <公告文本目录> <公告元数据>。"""
import gzip, json, re, sys
from pathlib import Path

NUM = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|-?\d+\.\d{1,2}|-?\d+")
ITEMS = [
    ("rev", ("营业总收入", "营业收入"), 1),
    ("np", ("归属于上市公司股东的净利润",), 1),
    ("kf", ("归属于上市公司股东的扣除非经常性损益的净利润", "归属于上市公司股东的扣除非经常性", "扣除非经常性损益后的净利润"), 1),
    ("ocf", ("经营活动产生的现金流量净额",), 1),
    ("roe", ("加权平均净资产收益率",), 0),
    ("capex", ("购建固定资产、无形资产和其他长期资产支付的现金", "购建固定资产、无形资产和其他长期资产所支付的现金"), 1),
    ("np_all", ("五、净利润", "四、净利润"), 1),
]


def flat(t):
    return re.sub(r"\s+", "", t)


def numbers(s):
    out = []
    for m in NUM.finditer(s):
        try:
            out.append(float(m.group().replace(",", "")))
        except ValueError:
            pass
    return out


def close(a, b, money):
    tol = 1.5 if money else 0.011
    return abs(a - b) <= tol


def find(pages, labels, value, money, width=130):
    """返回 (状态, 公告值, 页码)。先找标签后紧邻的第一个数；单位可能是元、千元或万元。"""
    first = None
    for lab in labels:
        for i, t in enumerate(pages):
            s = flat(t)
            for m in re.finditer(re.escape(lab), s):
                ns = [x for x in numbers(s[m.end():m.end() + width]) if not (x in (1, 2, 3, 4, 5, 6, 7, 8) or 1900 < x < 2100)]
                if not ns:
                    continue
                first = first or (ns[0], i + 1)
                if value is None:
                    continue
                for pos, x in enumerate(ns[:8]):
                    for scale in ((1, 1000, 10000) if money else (1,)):
                        if close(x * scale, value, money) or (money and scale > 1 and abs(x * scale - value) <= scale):
                            return ("一致" if pos == 0 else "一致-非首列", x * scale, i + 1)
    if first:
        return ("不一致", first[0], first[1])
    return ("无法验证", None, None)


def exact_page(pages, value):
    """按财报常见格式查找完整金额，避开换行截断标签的问题。"""
    if value is None:
        return None
    txt = f"{value:,.2f}"
    for i, t in enumerate(pages):
        if txt in flat(t):
            return i + 1
    return None


def parse_notice(text):
    s = flat(text)
    per10 = None
    for pat, mul in ((r"每10股派(?:发)?(?:现金(?:红利|股利)?)?(?:人民币)?([\d.]+)元", 1), (r"每股(?:派发)?现金红利(?:人民币)?([\d.]+)元", 10),
                     (r"每股派(?:发)?(?:现金)?(?:红利|股利)?(?:人民币)?([\d.]+)元", 10), (r"每股派([\d.]+)元", 10)):
        m = re.search(pat, s)
        if m:
            per10 = float(m.group(1)) * mul
            break
    total = None
    for pat in (r"(?:共计|合计|总计|共)(?:派发|分配|派送|分派)?(?:现金)?(?:红利|股利)?(?:总额)?(?:人民币)?([\d,.]+)(万)?元", r"派发现金(?:红利|股利)(?:总额)?(?:共计|合计)?(?:人民币)?([\d,.]+)(万)?元"):
        m = re.search(pat, s)
        if m:
            total = float(m.group(1).replace(",", "")) * (10000 if m.group(2) else 1)
            break
    m = re.search(r"除(?:权|息|权\(息\)|权（息）)[^0-9]{0,12}(20\d\d)[年\-/](\d{1,2})[月\-/](\d{1,2})", s)
    ex = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None
    if not ex:
        m = re.search(r"(20\d\d)/(\d\d)/(\d\d)", s)
        ex = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
    y = re.search(r"(20\d\d)年(?:度|年度|半年度|第三季度|前三季度|中期|三季度|第一季度|一季度)?", s)
    base = None
    m = re.search(r"(?:总股本|股本|基数)[^0-9]{0,24}([\d,]{7,})股", s)
    if m:
        base = int(m.group(1).replace(",", ""))
    return {"per10": per10, "total": total, "ex": ex, "base": base}


def main(snap, txt, meta_path):
    with gzip.open(snap / "inputs.jsonl.gz", "rt", encoding="utf-8") as f:
        inputs = {d["code"]: d for d in map(json.loads, f)}
    sample = json.loads((snap / "audit_sample.json").read_text())["sample"]
    meta = {(m["code"], m["kind"]): m for m in json.loads(Path(meta_path).read_text())}
    rows, notices = [], []
    for s in sample:
        c = s["code"]
        d = inputs[c]
        years = {r["year"]: r for r in d["years"]}
        for y in range(2021, 2026):
            pages = json.loads((txt / f"{c}_annual{y}.json").read_text())
            m = meta[(c, f"annual{y}")]
            for key, labs, money in ITEMS:
                v = years[str(y)].get(key)
                st, ext, pg = find(pages, labs, v, bool(money))
                later = None
                if st != "一致" and money and exact_page(pages, v):
                    st, ext, pg = "一致", v, exact_page(pages, v)
                if key == "roe" and v is None and any("不适用" in flat(t) and "加权平均净资产收益率" in flat(t) for t in pages):
                    st, ext = "一致-官方不适用", None
                if st not in ("一致", "一致-官方不适用"):
                    for ny in (y + 1, y + 2):
                        if ny > 2025 or later:
                            continue
                        nxt = json.loads((txt / f"{c}_annual{ny}.json").read_text())
                        pg2 = exact_page(nxt, v) if money else None
                        if not pg2:
                            st2, _, p2 = find(nxt, labs, v, bool(money))
                            pg2 = p2 if st2.startswith("一致") else None
                        if pg2:
                            later = {"page": pg2, "url": meta[(c, f"annual{ny}")]["url"], "year": ny}
                            st = "快照=后续年报调整后"
                orig = find(pages, labs, None, bool(money))[1] if st == "快照=后续年报调整后" else ext
                rows.append({"code": c, "name": s["name"], "period": str(y), "item": key, "snapshot": v, "official": orig,
                             "page": pg, "status": st, "url": m["url"], "later": later})
        q = json.loads((txt / f"{c}_q3_2026.json").read_text())
        main_row = d["source"]["main"][0]
        st, ext, pg = find(q, ("归属于上市公司股东的扣除非经常性损益的净利润", "扣除非经常性损益后的净利润", "归属于上市公司股东的扣除非经常性"),
                           main_row["KCFJCXSYJLR"], True, 300)
        rows.append({"code": c, "name": s["name"], "period": "2026Q3累计", "item": "kf", "snapshot": main_row["KCFJCXSYJLR"],
                     "official": ext, "page": pg, "status": st, "url": meta[(c, "q3_2026")]["url"]})
        for k, m in meta.items():
            if k[0] == c and k[1].startswith("impl_"):
                pages = json.loads((txt / f"{c}_{k[1]}.json").read_text())
                notices.append({"code": c, "name": s["name"], "title": m["title"], "url": m["url"], **parse_notice(" ".join(pages))})
    return rows, notices


if __name__ == "__main__":
    rows, notices = main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
    Path(sys.argv[1], "audit_rows.json").write_text(json.dumps({"rows": rows, "notices": notices}, ensure_ascii=False, indent=0))
    from collections import Counter
    print(Counter(r["status"] for r in rows))
    print(Counter((r["item"], r["status"]) for r in rows).most_common(30))
    print("notices", len(notices), sum(1 for n in notices if n["per10"]), sum(1 for n in notices if n["total"]), sum(1 for n in notices if n["ex"]))
