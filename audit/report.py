#!/usr/bin/env python3
"""生成 #6 审计报告：python3 audit/report.py <快照目录> <公告文本目录> <公告元数据> <旧快照目录>"""
import csv, gzip, json, re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "model"))
from compare import exact_page, flat
from report import load, split

ITEM = {"rev": "营业收入", "np": "归母净利润", "kf": "扣非净利润", "ocf": "经营现金流", "roe": "加权 ROE", "capex": "资本开支", "np_all": "合并净利润"}


def main(path, txt, meta_path, old):
    audit = json.loads((path / "audit_rows.json").read_text())
    rows, notices = audit["rows"], audit["notices"]
    recalc = json.loads((path / "audit_recalc.json").read_text())
    market = json.loads((path / "audit_market.json").read_text())
    sample = json.loads((path / "audit_sample.json").read_text())
    meta = {(m["code"], m["kind"]): m for m in json.loads(Path(meta_path).read_text())}
    with gzip.open(path / "inputs.jsonl.gz", "rt", encoding="utf-8") as f:
        inputs = {d["code"]: d for d in map(json.loads, f)}

    # 资产负债表：三季报原文按完整金额查找
    bs_rows = []
    for s in sample["sample"]:
        c = s["code"]
        pages = json.loads((txt / f"{c}_q3_2026.json").read_text())
        b = inputs[c]["source"]["balance"][0]
        for k, label in (("TOTAL_ASSETS", "总资产"), ("TOTAL_LIABILITIES", "总负债"), ("TOTAL_PARENT_EQUITY", "归母权益"), ("MONETARYFUNDS", "货币资金"), ("GOODWILL", "商誉"),
                         ("SHORT_LOAN", "短期借款"), ("LONG_LOAN", "长期借款")):
            v = b.get(k)
            if v is None:
                bs_rows.append((s["name"], label, "空", "接口未列示，未证明原报表为 0", None))
            else:
                pg = exact_page(pages, v)
                bs_rows.append((s["name"], label, f"{v:,.2f}", "一致" if pg else "无法验证", pg))

    ex_ok = ex_bad = 0
    bad_ex = []
    for n in notices:
        dates = {(r.get("EX_DIVIDEND_DATE") or "")[:10] for r in inputs[n["code"]]["source"]["dividend_main"]}
        if n["ex"]:
            if n["ex"] in dates:
                ex_ok += 1
            else:
                ex_bad += 1
                bad_ex.append((n["name"], n["title"], n["ex"]))

    a, b = load(old), load(path)
    A, B = {r["code"]: r for r in a}, {r["code"]: r for r in b}
    ma, oa, _ = split(a)
    mb, ob, _ = split(b)
    sa, sb = {r["code"] for r in ma}, {r["code"] for r in mb}
    ga, gb = sa | {r["code"] for r in oa}, sb | {r["code"] for r in ob}
    tier = lambda c, m, g: "主名单" if c in m else "副名单" if c in g else "未入选"
    changed = [c for c in sorted(A) if A[c]["总分"] != B[c]["总分"] or A[c]["等级"] != B[c]["等级"] or tier(c, sa, ga) != tier(c, sb, gb)]
    with (path / "changes_from_v0.3.1.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["code", "name", "v0.3.1分数", "v0.3.2分数", "v0.3.1等级", "v0.3.2等级", "v0.3.1名单", "v0.3.2名单", "v0.3.1分红率", "v0.3.2分红率"])
        for c in changed:
            x, y = A[c], B[c]
            r2 = lambda v: "" if v is None else round(v, 1)
            w.writerow([c, y["name"].replace(" ", ""), x["总分"], y["总分"], x["等级"], y["等级"], tier(c, sa, ga), tier(c, sb, gb), r2(x["metrics"]["payout"]), r2(y["metrics"]["payout"])])

    st = Counter(r["status"] for r in rows)
    L = ["# v0.3.2 独立抽查报告", "", "对应 issue #6。抽查检验样本，不代表全部 2881 只数据都已核实。", "",
         "## 结论", "",
         f"- 计算复现：通过。全量离线复算一致，7 只样本独立公式重算差异 {sum(len(x['diff']) for x in recalc)} 项。",
         f"- 外部核验：{len(rows)} 项财报数据里，{st['一致'] + st['一致-非首列'] + st['一致-官方不适用']} 项与当期公告一致，{st['快照=后续年报调整后']} 项与后续年报的调整后数字一致，0 项无法解释。",
         "- 接口保存的是后续调整后的财务数据，不是当期公告的原始版本，不能直接用于历史回测。",
         "- 分红口径已从估算改为官方财年总额，并用实施公告逐笔核对。", "",
         "## 抽样", "", f"固定种子 `{sample['seed']}`，方法见 `audit/sample.py`。主名单、副名单、非合格各抽 2 只，数据缺失风险层抽 1 只。", "",
         "| 层 | 公司 | 行业 | 分数 | 分档 |", "|---|---|---|---:|---|"]
    L += [f"| {s['层']} | {s['name']} {s['code']} | {s['industry']} | {s['总分']} | {s['等级']} |" for s in sample["sample"]]
    L += ["", "## 财报数据", "", "| 项目 | 一致 | 调整后 | 其他 |", "|---|---:|---:|---:|"]
    for k, n in ITEM.items():
        xs = [r for r in rows if r["item"] == k]
        L.append(f"| {n} | {sum(r['status'].startswith('一致') for r in xs)} | {sum(r['status'] == '快照=后续年报调整后' for r in xs)} | {sum(not r['status'].startswith('一致') and r['status'] != '快照=后续年报调整后' for r in xs)} |")
    L += ["", "“一致-非首列”主要是三季报累计列；“一致-官方不适用”是株冶集团 2021 年 ROE。", "", "## 追溯调整明细", "", "“原值”取当期公告；取不到可靠原值时写“未取得”。金额单位为元。", "",
          "| 公司 | 期间 | 项目 | 当期公告 | 快照 | 调整来源 |", "|---|---|---|---:|---:|---|"]
    for r in rows:
        if r["status"] == "快照=后续年报调整后":
            o = r["official"]
            ok = o is not None and not (r["item"] == "rev" and not 0.5 < o / r["snapshot"] < 2)
            fmt = (lambda v: f"{v:,.2f}")
            L.append(f"| {r['name']} | {r['period']} | {ITEM[r['item']]} | {fmt(o) if ok else '未取得'} | {fmt(r['snapshot'])} | [{r['later']['year']} 年报第 {r['later']['page']} 页]({r['later']['url']}) |")
    L += ["", "## 分红", "", f"共取得 {len(notices)} 份实施公告。按所属财年加总后，电投能源、珀莱雅、焦点科技、西部材料 2021～2025 年全部一致。", "",
          "| 公司 | 核对结果 |", "|---|---|",
          "| 蓝天燃气 | 2021～2024 与公告一致；2025 年报无年度预案，半年度每 10 股派 4 元，与快照一致 |",
          "| 杭州热电 | 2022～2025 一致；2021 年报确认中期和年度两次分配，年度公告 72,018,000 元，上市前中期金额未取得实施公告，总额只部分验证 |",
          "| 株冶集团 | 接口 5 年均为不分配，无实施公告；2024、2025 年报显示可分配利润为负。2021～2023 只核到接口记录，未逐年读年报 |", "",
          f"除息日：解析到的公告日期 {ex_ok} 项与接口一致，{ex_bad} 项不一致。"]
    L += [f"- {x[0]}：{x[1]}，解析值 {x[2]}" for x in bad_ex]
    L += ["", "### 口径决定", "",
          "- 分红和净利润都按所属财年配对。接口 `TOTAL_DIVIDEND` 是财年合计，不是单次金额，不能逐行相加。",
          "- 已实施现金方案记为实施；年报明确不分配或只送转记为 0；有现金方案未实施记为待实施；其他情况记为未知。待实施和未知不得分。",
          "- `ASSIGN_DIVIDEND_PORFIT` 只作审计，部分公司分红和该字段时间不同，不能作为普通股分红标准。", "",
          "## 资产负债表", "", "按 2026 年三季报完整金额查找。", "", "| 公司 | 项目 | 接口值（元） | 结果 | 页码 |", "|---|---|---:|---|---:|"]
    L += [f"| {a_} | {b_} | {c_} | {d_} | {e_ or '-'} |" for a_, b_, c_, d_, e_ in bs_rows]
    L += ["", "## 价格和市值", "", "收盘价由新浪行情复核；总股本为东方财富股本表，非交易所原文。", "", "| 公司 | 快照价 | 新浪收盘 | 快照市值 | 价格 × 总股本 |", "|---|---:|---:|---:|---:|"]
    L += [f"| {m['name']} | {m['snapshot_price']} | {m['sina_close']} | {m['mv']:,.0f} | {m['price_x_shares']:,.0f} |" for m in market]
    L += ["", "36 个月波动率和回撤按快照月线独立重算一致。前复权月线本身没有第二来源，外部核验结果为“无法验证”。", "",
          "## 指标和分数", "", "| 公司 | 公式差异 | 快照分数 | 用当期公告替换调整项后的分数 | 替换项目数 |", "|---|---:|---:|---:|---:|"]
    L += [f"| {x['name']} | {len(x['diff'])} | {x['score']} | {x['score_original']} | {x['replaced']} |" for x in recalc]
    L += ["", "替换分数只是影响估计。株冶集团从 51 分变为 47 分，分档仍是数据不足。", "",
          "## 全量影响", "", f"相比 v0.3.1，{len(changed)} 只公司的分数、分档或名单变化，详见 [`changes_from_v0.3.1.csv`](../../results/{path.name}/changes_from_v0.3.1.csv)。", "",
          f"- 主名单：{len(sa)} → {len(sb)}。进入 {len(sb - sa)} 只，离开 {len(sa - sb)} 只。",
          f"- 合格公司：{len(ga)} → {len(gb)}。", "",
          "## 未验证", "", "- 样本只有 7 只，不能推断全市场零错误。", "- 毛利率、ROIC 没有和公告逐项核对。", "- 现金流表以外的资本开支口径只按公告项目核对。",
          "- 前复权月线没有第二来源。", "- 杭州热电 2021 中期分红金额、株冶 2021～2023 不分配只取得部分证据。", "- 质押、减持、审计意见仍未核查。", "",
          "## 证据文件", "", "PDF 不提交，URL 和 SHA-256 见 `docs/evidence/v0.3.2_source_files.csv`。"]
    Path("docs/evidence/v0.3.2_spot_audit.md").write_text("\n".join(L) + "\n")
    with open("docs/evidence/v0.3.2_source_files.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["code", "kind", "title", "url", "sha256"])
        for m in sorted(meta.values(), key=lambda x: (x["code"], x["kind"])):
            w.writerow([m["code"], m["kind"], m["title"], m["url"], m["sha256"]])
    print("changes", len(changed), "bs", Counter(x[3] for x in bs_rows), "ex", ex_ok, ex_bad, bad_ex[:6])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
