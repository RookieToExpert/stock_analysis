#!/usr/bin/env python3
"""离线检查现有下载的日历/事件/价格一致性；不调用下载器、不补齐未知值。"""
import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from total_return import analyze
from calendar_coverage import calendar_gap_reason


def audit(root, calendar, codes=None):
    paths = sorted(root.glob('s[hz].*.json')) if codes is None else [root/(c+'.json') for c in sorted(set(codes))]
    rows=[]
    for path in paths:
        entry={'code':path.stem}
        try:
            raw=path.read_bytes();entry['sha256']=hashlib.sha256(raw).hexdigest()
            data=json.loads(raw)
            if data.get('code')!=path.stem:raise ValueError('security identity mismatch')
            gap=calendar_gap_reason(data,calendar)
            if gap:raise ValueError(gap)
            result=analyze(data,calendar['start'],calendar['end'])
            entry.update(status='ok',metrics=result['metrics'],redundant_adjustment_dates=result['redundant_adjustment_dates'])
        except (OSError,ValueError,KeyError,TypeError) as exc:
            entry.update(status='failed',reason=str(exc))
        rows.append(entry)
    return {'scope':'fixed existing file list; local data only, no supplemental source or issuer audit',
            'calendar':calendar,'files':len(paths),'counts':dict(Counter(r['status'] for r in rows)),
            'failures':dict(Counter(r['reason'].rsplit(' ',1)[0] if r['reason'][-10:-6].isdigit() else r['reason']
                                    for r in rows if r['status']=='failed')), 'rows':rows}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('calendar',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--codes',type=Path,help='JSON list of security codes to freeze the audit cohort')
    args=p.parse_args()
    with gzip.open(args.calendar,'rt') as f:cal=json.load(f)
    result=audit(args.root,cal,json.loads(args.codes.read_text()) if args.codes else None)
    with gzip.open(args.output,'wt') as f:json.dump(result,f,ensure_ascii=False)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','calendar')},ensure_ascii=False))
