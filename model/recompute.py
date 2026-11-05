#!/usr/bin/env python3
"""离线复算：python3 model/recompute.py results/<目录>。只读 inputs.jsonl(.gz)，不联网。"""
import gzip, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from score import evaluate


def read_lines(path):
    gz = path / "inputs.jsonl.gz"
    if gz.exists():
        with gzip.open(gz, "rt", encoding="utf-8") as f:
            return f.read().splitlines()
    return (path / "inputs.jsonl").read_text().splitlines()


def norm(x):
    return json.loads(json.dumps(x, ensure_ascii=False, default=str))


def main(path):
    expected = {}
    for line in (path / "raw.jsonl").read_text().splitlines():
        r = json.loads(line)
        if "error" not in r:
            expected[r["code"]] = r
    bad, seen = [], set()
    for line in read_lines(path):
        d = json.loads(line)
        seen.add(d["code"])
        if norm(evaluate(d)) != expected.get(d["code"]):
            bad.append(d["code"])
    lost = sorted(set(expected) - seen)
    print(f"inputs {len(seen)} results {len(expected)} mismatch {len(bad)} no_input {len(lost)}", bad[:10], lost[:10])
    return 1 if bad or lost else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
