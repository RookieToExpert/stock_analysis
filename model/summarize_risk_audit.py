#!/usr/bin/env python3
"""Summarize saved supplement checks; never counts an unresolved action as valid."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path


def summarize(directory):
    records=[]
    for p in sorted(directory.glob('s[hz].*.json.gz')):
        with gzip.open(p,'rt') as f:records.append(json.load(f))
    failures=[]
    for r in records:
        if r['status']=='reconstructed':continue
        error=r.get('error','')
        category=('unexplained_reference_price' if 'unexplained reference price' in error
                  else 'conflicting_action' if 'conflict' in error
                  else 'missing_action' if 'adjustment without' in error
                  else 'other')
        failures.append({'code':r['code'],'category':category,'error':error})
    gaps=json.loads((directory/'calendar-gaps.json').read_text())
    result={'scope':'fixed 3510-stock cohort; consistency audit, not issuer certification',
            'supplement_targets':len(records),'reconstructed':sum(r['status']=='reconstructed' for r in records),
            'failed':len(failures),'failure_categories':dict(Counter(r['category'] for r in failures)),
            'structural_window_exclusions':gaps['counts'],'failures':failures,
            'issuer_certified':False,'formal_backtest_allowed':False}
    (directory/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    r=summarize(p.parse_args().directory)
    print(json.dumps({k:v for k,v in r.items() if k!='failures'},ensure_ascii=False))
