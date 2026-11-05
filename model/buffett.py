#!/usr/bin/env python3
"""研究线 B、C：python3 model/buffett.py results/<目录>。只读快照，不联网。"""
import csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from recompute import read_lines
from rules import _median, clean_years, metrics, missing_fields, vetoes

TOP = 20


def factors(d):
    """返回研究因子；任何一项未知都用 None。"""
    m = metrics(d)
    y = clean_years(d.get("years") or [])
    roics = [r.get("roic") for r in y]
    roic = _median(roics) if len(roics) == 5 and None not in roics else None
    retain = None
    if len(y) == 5 and all(r.get("kf") is not None and r.get("np") is not None and r.get("paid") is not None for r in y):
        kept = sum(r["np"] - r["paid"] for r in y[1:])
        if kept > 0:
            retain = (y[0]["kf"] - y[4]["kf"]) / kept
    return {"roic": roic, "ocf_np": m["ocf_np"], "retain": retain, "debt_ratio": m["debt_ratio"], "vol": m["vol"],
            "ep_norm": m["ep_norm"], "fcf_yield": m["fcf_yield"]}


def ranks(rows, key, high=True):
    """百分位 0～1，越大越好；相同值取平均排名。"""
    vals = sorted(r[key] for r in rows)
    n = len(vals)
    out = {}
    for r in rows:
        v = r[key]
        lo = sum(x < v for x in vals)
        hi = sum(x <= v for x in vals)
        p = (lo + hi - 1) / 2 / (n - 1) if n > 1 else 0.5
        out[r["code"]] = p if high else 1 - p
    return out


def rank_qsc(rows):
    q = [ranks(rows, k) for k in ("roic", "ocf_np", "retain")]
    s = [ranks(rows, "debt_ratio", False), ranks(rows, "vol", False)]
    c = [ranks(rows, k) for k in ("ep_norm", "fcf_yield")]
    avg = lambda xs, code: sum(x[code] for x in xs) / len(xs)
    for r in rows:
        r["Q"], r["S"], r["C"] = (avg(x, r["code"]) for x in (q, s, c))
        r["score"] = (r["Q"] + r["S"] + r["C"]) / 3
    return rows


def qv_pool(rows):
    return [r for r in rows if r["roic"] >= 10 and r["ocf_np"] >= 0.8 and r["debt_ratio"] <= 60]


def pick(rows):
    """按 score 取前 20，单一行业最多 5 只（25%）。"""
    out, count = [], {}
    for r in sorted(rows, key=lambda x: (-x["score"], -x["mv"])):
        if count.get(r["industry"], 0) >= 5:
            continue
        count[r["industry"]] = count.get(r["industry"], 0) + 1
        out.append(r)
        if len(out) == TOP:
            break
    return out


def build(inputs):
    rows, skipped = [], 0
    for d in inputs:
        m = metrics(d)
        if vetoes(d, m) or missing_fields(d):
            continue
        f = factors(d)
        if any(v is None for v in f.values()):
            skipped += 1
            continue
        rows.append({"code": d["code"], "name": d["name"].replace(" ", ""), "industry": d["industry"], "mv": d["mv"], **f})
    rank_qsc(rows)
    pool = [dict(r) for r in qv_pool(rows)]
    cheap = {k: ranks(pool, k) for k in ("ep_norm", "fcf_yield")} if pool else {}
    for r in pool:
        r["score"] = sum(cheap[k][r["code"]] for k in cheap) / 2
    return pick(pool), pick(rows), len(rows), len(pool), skipped


def main(path):
    b, c, n, nb, skipped = build(json.loads(x) for x in read_lines(path))
    fields = ["策略", "code", "name", "industry", "mv", "score", "roic", "ocf_np", "retain", "debt_ratio", "vol", "ep_norm", "fcf_yield"]
    with (path / "buffett_research.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for tag, xs in (("B", b), ("C", c)):
            for r in xs:
                w.writerow([tag] + [round(r[k], 4) if isinstance(r[k], float) else r[k] for k in fields[1:]])
    print("complete", n, "qv pool", nb, "unknown factor", skipped, "B", len(b), "C", len(c))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
