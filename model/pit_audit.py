#!/usr/bin/env python3
"""只读审计已下载文件；逐评价日检查五年年报输入覆盖，不联网、不写下载目录。
python3 model/pit_audit.py DATA_DIR OUTPUT_JSON
这只是覆盖门槛，不能代替官方公告、ST、原始版本及全收益基准验收。
"""
import json
import sys
from pathlib import Path
from financial_evidence import verified_operating_cash_flow

TABLES=('profit','cash','balance','dupont')
REQUIRED={'profit':('netProfit','roeAvg','gpMargin','MBRevenue','totalShare'),
          'cash':('CFOToNP',),'balance':('liabilityToAsset',),'dupont':('dupontPnitoni',)}


def annual_missing(data, day):
    end=int(day[:4])-1
    errors=[]
    for table in TABLES:
        by={}
        for row in data.get('fin',{}).get(table,[]):
            if row.get('pubDate','') and row['pubDate']<day:
                by.setdefault(row.get('statDate'),[]).append(row)
        for year in range(end-4,end+1):
            period=f'{year}-12-31';xs=by.get(period,[])
            if len(xs)!=1:
                errors.append(f'{table}:{period}:rows={len(xs)}');continue
            for field in REQUIRED[table]:
                if table=='cash' and field=='CFOToNP' and verified_operating_cash_flow(data,period,day):
                    continue
                try:
                    from math import isfinite
                    if not isfinite(float(xs[0].get(field))): raise ValueError()
                except (ValueError,TypeError):errors.append(f'{table}:{period}:{field}')
    return errors


def audit(root):
    universe=json.loads((root/'universe.json').read_text())
    files={p.stem:p for p in root.glob('*.json') if p.name!='universe.json'}
    report={d:{'universe':len(set(codes)),'missing_files':[],'annual_incomplete':[]} for d,codes in universe.items()}
    memberships={}
    for day,codes in universe.items():
        for code in set(codes):memberships.setdefault(code,[]).append(day)
    read_errors={}
    for code,days in memberships.items():
        if code not in files:
            for day in days:report[day]['missing_files'].append(code)
            continue
        try:
            data=json.loads(files[code].read_text())
            if data.get('code')!=code:raise ValueError('code mismatch')
        except (OSError,ValueError) as exc:
            read_errors[code]=str(exc)
            for day in days:report[day]['missing_files'].append(code)
            continue
        for day in days:
            missing=annual_missing(data,day)
            if missing:report[day]['annual_incomplete'].append({'code':code,'reasons':missing})
    for day,entry in report.items():
        n=len(entry['missing_files'])+len(entry['annual_incomplete'])
        entry.update(missing_count=n,missing_fraction=n/entry['universe'] if entry['universe'] else 1,
                     preliminary_coverage_pass=bool(entry['universe']) and n/entry['universe']<=.05)
    return {'scope':'all listed stocks before IPO age/industry eligibility; diagnostic not final strategy gate; fixed file list at start', 'downloaded_files':len(files),
            'read_errors':read_errors,'evaluations':report,
            'backtest_allowed':False,
            'remaining_gates':['official financial/dividend audit','ST announcement audit',
                               'unrestated vintage verification','total-return benchmarks','daily and action coverage']}


if __name__=='__main__':
    result=audit(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('downloaded',result['downloaded_files'])
    for day,r in sorted(result['evaluations'].items()):
        print(day,r['universe'],r['missing_count'],f"{r['missing_fraction']:.1%}",r['preliminary_coverage_pass'])
    print('backtest_allowed=False: coverage is not the complete data gate')
