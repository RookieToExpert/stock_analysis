#!/usr/bin/env python3
"""#6 固定抽样：python3 audit/sample.py results/<目录>。分层后用固定种子抽取，不按结果挑选。"""
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "model"))
from report import load, split

SEED = 20261105


def strata(rows):
    a, b, _ = split([r for r in rows if "error" not in r])
    main, other = {r["code"] for r in a}, {r["code"] for r in b}
    code = lambda r: r["code"]
    return {
        "主名单": sorted(a, key=code),
        "副名单": sorted(b, key=code),
        "非合格": sorted([r for r in rows if r["等级"] in ("观察", "放弃") and r["code"] not in main | other], key=code),
        "数据缺失风险": sorted([r for r in rows if r["等级"] == "数据不足"], key=code),
    }


def main(path):
    rng = random.Random(SEED)
    picks = []
    for name, xs in strata(load(path)).items():
        n = 1 if name == "数据缺失风险" else 2
        for r in rng.sample(xs, min(n, len(xs))):
            picks.append({"层": name, "code": r["code"], "name": r["name"].replace(" ", ""), "industry": r["industry"],
                          "总分": r["总分"], "等级": r["等级"]})
    (path / "audit_sample.json").write_text(json.dumps({"seed": SEED, "sample": picks}, ensure_ascii=False, indent=1))
    for p in picks:
        print(p)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
