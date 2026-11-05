#!/usr/bin/env python3
"""全 A 筛选：python3 model/screen.py [--limit N] [--out 目录]。逐只写入输入快照和结果，可断点续跑。"""
import json, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rules import FINANCIAL
from score import evaluate, fetch, get

FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"  # 沪深主板、创业板、科创板，不含北交所
OUT = Path(__file__).parent.parent / "results" / f"{date.today().isoformat()}-v0.3"
if "--out" in sys.argv:
    OUT = Path(sys.argv[sys.argv.index("--out") + 1])


def universe():
    items, page = [], 1
    while True:
        d = get(f"https://push2.eastmoney.com/api/qt/clist/get?pn={page}&pz=100&po=0&np=1&fltt=2&fid=f12"
                f"&fs={FS}&fields=f12,f14,f2,f20,f100,f26")["data"]
        diff = d.get("diff") or []
        items += diff
        if not diff or len(items) >= d["total"]:
            return list({x["f12"]: x for x in items}.values()), d["total"]
        page += 1
        time.sleep(0.2)


def prefilter(items):
    """返回 (待打分, 各剔除原因计数)。市值分界在全部有效报价股票上计算。"""
    live = [x for x in items if isinstance(x.get("f20"), (int, float)) and x["f20"] > 0]
    mvs = sorted(x["f20"] for x in live)
    cut = mvs[int(len(mvs) * 0.3)]
    cutoff_date = int(f"{date.today().year - 5}{date.today():%m%d}")
    keep, drop = [], {"无有效报价": len(items) - len(live), "ST/退市": 0, "金融股": 0, "上市不满5年": 0, "市值最小30%": 0}
    for x in live:
        name, ind, listed = x.get("f14") or "", x.get("f100") or "", x.get("f26")
        if "ST" in name.upper() or "退" in name:
            drop["ST/退市"] += 1
        elif any(k in ind for k in FINANCIAL):
            drop["金融股"] += 1
        elif not isinstance(listed, int) or listed > cutoff_date:
            drop["上市不满5年"] += 1
        elif x["f20"] < cut:
            drop["市值最小30%"] += 1
        else:
            keep.append(x)
    return keep, drop, cut


def one(x):
    code = x["f12"]
    quote = {"f43": x["f2"] * 100, "f58": x["f14"], "f116": x["f20"], "f127": x["f100"]}
    time.sleep(0.3)
    for attempt in range(2):
        try:
            d = fetch(code, quote)
            return {"input": d, "result": evaluate(d)}
        except Exception as e:
            err = repr(e)
            time.sleep(3)
    return {"result": {"code": code, "error": err}}


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "universe_list.json"
    if cache.exists():  # 同一天只拉一次全市场列表
        items = json.loads(cache.read_text())
        total = len(items)
    else:
        items, total = universe()
        cache.write_text(json.dumps(items, ensure_ascii=False))
    keep, drop, cut = prefilter(items)
    (OUT / "universe.json").write_text(json.dumps(
        {"列表返回": len(items), "接口总数": total, "剔除": drop, "待打分": len(keep), "市值分界": cut}, ensure_ascii=False, indent=1))
    print("universe", len(items), total, drop, "keep", len(keep), "cut", cut, flush=True)
    raw = OUT / "raw.jsonl"
    done = set()
    if raw.exists():
        for line in raw.read_text().splitlines():
            r = json.loads(line)
            if "error" not in r:
                done.add(r["code"])
    todo = [x for x in keep if x["f12"] not in done][:limit]
    lock, n, fails = threading.Lock(), [0], [0]
    with raw.open("a") as f, (OUT / "inputs.jsonl").open("a") as fin, ThreadPoolExecutor(2) as ex:
        for fu in as_completed([ex.submit(one, x) for x in todo]):
            pair = fu.result()
            r = pair["result"]
            with lock:
                if "input" in pair:
                    fin.write(json.dumps(pair["input"], ensure_ascii=False, default=str) + "\n")
                    fin.flush()
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
                f.flush()
                n[0] += 1
                fails[0] = fails[0] + 1 if "error" in r else 0
                if n[0] % 200 == 0:
                    print(n[0], "/", len(todo), flush=True)
                if fails[0] >= 20:  # 大概率被限流，停下而不是继续请求
                    print("stop: 连续失败20只", r.get("error"), flush=True)
                    ex.shutdown(wait=False, cancel_futures=True)
                    break
    print("done", n[0], flush=True)


if __name__ == "__main__":
    main()
