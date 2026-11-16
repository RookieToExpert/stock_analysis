#!/usr/bin/env python3
"""同一输入快照对比 v0.3.2/v0.3.3；不是历史时点回测。
用法：python3 model/compare_versions.py results/2026-11-05-v0.3.2 2026-11-05
日期必须是快照实际评价日，不得用它伪造历史可用性。
"""
import collections
import copy
import json
import sys
from datetime import date
from pathlib import Path
from recompute import read_lines
from score import evaluate
from rules import recent_details


def compare(path, as_of):
    date.fromisoformat(as_of)
    counts, grades = collections.Counter(), collections.Counter()
    for line in read_lines(path):
        original = json.loads(line)
        if original.get('model_version') not in (None, '0.3.2'):
            raise ValueError('Expected v0.3.2 input')
        old = evaluate(original)
        updated = copy.deepcopy(original)
        updated.update(model_version='0.3.3', as_of=as_of)
        updated.update(recent_details(updated.get('source', {}).get('main', [])))
        new = evaluate(updated)
        counts['inputs'] += 1
        counts['score_changed'] += old['总分'] != new['总分']
        counts['grade_changed'] += old['等级'] != new['等级']
        counts['recent_changed'] += old['近期状态'] != new['近期状态']
        counts['quarter_missing'] += not updated['quarter_known']
        grades[old['等级'] + ' → ' + new['等级']] += 1
    return {'counts': dict(counts), 'grades': dict(grades)}


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(json.dumps(compare(Path(sys.argv[1]), sys.argv[2]), ensure_ascii=False, indent=2))
