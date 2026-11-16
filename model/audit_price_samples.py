#!/usr/bin/env python3
"""离线审计保存的腾讯月线样本，不证明全收益正确。"""
import json
from pathlib import Path
from price_risk import calculate


def audit(root):
    out=[]
    for code in ('601919','601225'):
        series={}
        for mode in ('qfq','hfq','raw'):
            doc=json.loads((root/f'{code}-tx-{mode}.json').read_text())
            rows=doc['response']['data']['sh'+code][('' if mode=='raw' else mode)+'month']
            series[mode]={r[0]:float(r[2]) for r in rows if r[0]<'2026-11-01'}
            r=calculate([','.join(row[:5]) for row in rows],'2026-11-16')
            out.append({'code':code,'source':'tencent','mode':mode,
                        'reference_date':r['reference_date'],'drawdown':r['drawdown'],'vol':r['vol']})
        dates=sorted(set(series['qfq']) & set(series['hfq']))
        delta=[series['hfq'][d]-series['qfq'][d] for d in dates]
        out.append({'code':code,'hfq_minus_qfq_close_range':[min(delta),max(delta)]})
    return out


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]/'docs/evidence/price_probe'
    print(json.dumps(audit(root),ensure_ascii=False,indent=2))
