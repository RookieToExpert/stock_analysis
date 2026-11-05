#!/usr/bin/env python3
"""把快照的分红改为官方财年口径：python3 model/patch_dividends.py <旧目录> <新目录>。只补分红，其他输入不变。"""
import gzip, json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rules import fiscal_dividends
from score import dividend_rows, evaluate


def one(d):
    time.sleep(0.2)
    last = None
    for _ in range(2):
        try:
            rows = dividend_rows(d["code"])
            break
        except Exception as e:
            last = e
            time.sleep(3)
    else:
        return d["code"], None, repr(last)
    fy = fiscal_dividends(rows)
    d["source"]["dividend_main"] = rows
    d["source"]["dividend_event_estimate"] = {r["year"]: r["paid"] for r in d["years"]}
    for r in d["years"]:
        x = fy.get(r["year"], {"paid": None, "status": "未知"})
        r["paid"], r["paid_status"] = x["paid"], x["status"]
    return d["code"], d, None


def main(old, new):
    new.mkdir(parents=True, exist_ok=True)
    done = set()
    fin = new / "inputs.jsonl"
    if fin.exists():
        done = {json.loads(l)["code"] for l in fin.read_text().splitlines()}
    with gzip.open(old / "inputs.jsonl.gz", "rt", encoding="utf-8") as f:
        todo = [d for d in map(json.loads, f) if d["code"] not in done]
    n = fails = 0
    with fin.open("a") as a, (new / "raw.jsonl").open("a") as b, ThreadPoolExecutor(3) as ex:
        for fu in as_completed([ex.submit(one, d) for d in todo]):
            code, d, err = fu.result()
            n += 1
            if err:
                fails += 1
                print("fail", code, err, flush=True)
                if fails >= 20:
                    ex.shutdown(wait=False, cancel_futures=True)
                    break
                continue
            fails = 0
            a.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
            a.flush()
            b.write(json.dumps(evaluate(d), ensure_ascii=False, default=str) + "\n")
            b.flush()
            if n % 300 == 0:
                print(n, "/", len(todo), flush=True)
    print("done", n, flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
