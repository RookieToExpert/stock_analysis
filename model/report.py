#!/usr/bin/env python3
"""由 raw.jsonl 生成两层名单：python3 model/report.py results/<目录>"""
import csv, json, statistics, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from recompute import read_lines


def load(path):
    last = {}
    for line in read_lines(path, "raw"):
        r = json.loads(line)
        if r["code"] not in last or "error" not in r:
            last[r["code"]] = r
    return list(last.values())


def split(rows):
    """主名单：蓝筹条件 + 合格 + 蓝筹池内波动率不属于最高 30%。其余合格公司进副名单。"""
    good = [r for r in rows if r.get("等级") == "合格"]
    pool = sorted(r["metrics"]["vol"] for r in rows if r.get("蓝筹条件") and r.get("等级") in ("合格", "观察")
                  and r["metrics"].get("vol") is not None)
    cut = pool[int(len(pool) * 0.7)] if pool else None
    main, other = [], []
    for r in good:
        vol = r["metrics"].get("vol")
        (main if r.get("蓝筹条件") and vol is not None and cut is not None and vol <= cut else other).append(r)
    key = lambda r: (-r["总分"], -r["mv"])
    return sorted(main, key=key), sorted(other, key=key), cut


def line(r):
    m = r["metrics"]
    f = lambda v: "-" if v is None else f"{v:.1f}"
    note = "；".join(r["近期状态"] + r["人工警示"] + [f"{x}未知" for x in r["状态未知"]]) or "-"
    return (f"| {r['code']} | {r['name'].replace(' ', '')} | {r['industry']} | {r['mv'] / 1e8:.0f} | {r['总分']} | {r['动作']} | "
            f"{f(m['roe_med'])} | {f(m['ep'])} | {f(m['ep_norm'])} | {f(m['sust_yield'])} | {f(m['payout'])} | {f(m['vol'])} | {note} |")


HEAD = ("| 代码 | 名称 | 行业 | 市值(亿) | 分数 | 下一步 | ROE中位% | 盈利收益率% | 5年平均盈利收益率% | 可持续股息率% | 5年分红率% | 波动率% | 需关注 |\n"
        "|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|")


def main(path):
    rows = load(path)
    uni = json.loads((path / "universe.json").read_text())
    ok = [r for r in rows if "error" not in r]
    errs = [r for r in rows if "error" in r]
    grades = Counter(r["等级"] for r in ok)
    a, b, cut = split(ok)
    fields = ["层级", "code", "name", "industry", "price", "mv", "总分", "质量", "估值", "回报", "安全", "动作"]
    with (path / "list.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(fields + ["近期状态", "人工警示"])
        for tier, xs in (("主名单", a), ("副名单", b)):
            for r in xs:
                w.writerow([tier] + [r[k] for k in fields[1:]] + ["；".join(r["近期状态"]), "；".join(r["人工警示"])])
    missing = Counter(x.split("缺")[0] for r in ok if r["等级"] == "数据不足" for x in r["缺数据"])
    text = f"""# 全 A 筛选结果 v0.3

**这不是买入清单。** 分数未经回测，所有公司的审计、立案、质押、减持和资金占用都还没有人工核查。

- 数据日期：{path.name[:10]}
- 输入快照和校验信息：`inputs.jsonl.gz`、`manifest.json`
- 全市场 {uni['列表返回']} 只，进入打分 {uni['待打分']} 只，成功 {len(ok)} 只，失败 {len(errs)} 只
- 预筛剔除：{uni['剔除']}
- 分档：{dict(grades)}
- 蓝筹池波动率上限：{'-' if cut is None else f'{cut:.1f}%'}

## 主名单：稳健分红蓝筹（{len(a)} 只）

{HEAD}
{chr(10).join(line(r) for r in a) or '无'}

## 副名单：其他好公司（{len(b)} 只）

{HEAD}
{chr(10).join(line(r) for r in b) or '无'}
"""
    (path / "README.md").write_text(text)
    print(len(ok), len(errs), dict(grades), "main", len(a), "other", len(b), "vol cut", cut, "missing", missing.most_common(6))
    return a, b


if __name__ == "__main__":
    main(Path(sys.argv[1]))
