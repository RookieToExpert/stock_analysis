#!/usr/bin/env python3
"""独立重算样本指标：不调用 rules.metrics，用来检查计算链。python3 audit/recalc.py <快照目录>"""
import gzip, json, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "model"))
from rules import metrics, score, vetoes


def independent(d):
    y = d["years"][:5]
    ks = lambda k: [r[k] for r in y]
    ttm_rows = d["source"]["main"]
    latest = ttm_rows[0]
    year = latest["REPORT_DATE"][:4]
    prev = [r for r in ttm_rows if r["REPORT_DATE"][:10] == f"{int(year) - 1}{latest['REPORT_DATE'][4:10]}"][0]
    annual = [r for r in ttm_rows if r["REPORT_DATE"][:10] == f"{int(year) - 1}-12-31"][0]
    ttm = latest["KCFJCXSYJLR"] + annual["KCFJCXSYJLR"] - prev["KCFJCXSYJLR"]
    fcf = (sum(ks("ocf")) - sum(ks("capex"))) / 5
    closes = d["closes"]
    rets = [closes[i + 1] / closes[i] - 1 for i in range(len(closes) - 1)]
    out = {"roe_med": statistics.median(ks("roe")) if None not in ks("roe") else None, "ocf_np": sum(ks("ocf")) / sum(ks("np_all")),
           "ep": ttm / d["mv"] * 100, "ep_norm": sum(ks("kf")) / 5 / d["mv"] * 100, "fcf_yield": fcf / d["mv"] * 100,
           "payout": sum(ks("paid")) / sum(ks("np")) * 100 if None not in ks("paid") else None,
           "vol": statistics.stdev(rets) * 12 ** .5 * 100,
           "drawdown": (1 - d["price"] / d["high36"]) * 100}
    if None not in ks("paid"):
        out["sust_yield"] = max(min(sum(ks("paid")) / 5, fcf, ttm), 0) / d["mv"] * 100
    return out


def main(path):
    with gzip.open(path / "inputs.jsonl.gz", "rt", encoding="utf-8") as f:
        inputs = {d["code"]: d for d in map(json.loads, f)}
    with gzip.open(path / "raw.jsonl.gz", "rt", encoding="utf-8") as f:
        raw = {r["code"]: r for r in map(json.loads, f)}
    sample = json.loads((path / "audit_sample.json").read_text())["sample"]
    audit = json.loads((path / "audit_rows.json").read_text())
    out = []
    for s in sample:
        c = s["code"]
        ind, rep = independent(inputs[c]), raw[c]["metrics"]
        diff = {k: (v, rep.get(k)) for k, v in ind.items()
                if (v is None) != (rep.get(k) is None) or (v is not None and abs(v - rep[k]) > 1e-6)}
        # 用原始公告值替换被追溯调整的年报项目，只作影响估计
        d = json.loads(json.dumps(inputs[c]))
        used = 0
        for r in audit["rows"]:
            if r["code"] == c and r["status"] == "快照=后续年报调整后" and r["official"] is not None:
                if r["item"] == "rev" and not 0.5 < r["official"] / r["snapshot"] < 2:
                    continue
                for y in d["years"]:
                    if y["year"] == r["period"]:
                        y[r["item"]] = r["official"]
                        used += 1
        m0, m1 = metrics(inputs[c]), metrics(d)
        out.append({"code": c, "name": s["name"], "层": s["层"], "diff": diff, "score": score(m0)["总分"], "score_original": score(m1)["总分"],
                    "replaced": used, "veto_original": vetoes(d, m1), "report_total": raw[c]["总分"], "grade": raw[c]["等级"]})
    (path / "audit_recalc.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for x in out:
        print(x["name"], x["层"], "formula diffs", len(x["diff"]), "score", x["score"], "orig", x["score_original"], "replaced", x["replaced"], x["veto_original"], list(x["diff"].items())[:2])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
