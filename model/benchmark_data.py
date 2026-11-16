"""官方全收益基准标准化：按独立交易日对齐，禁止补缺日或价格指数替代。"""
import math
from datetime import datetime

ALLOWED={'H00300','H00922'}


def normalize(document,code,days):
    if code not in ALLOWED:raise ValueError('not an approved total-return benchmark')
    response=document['response']
    if str(response.get('code'))!='200':raise ValueError('benchmark response error')
    by={}
    for row in response.get('data',[]):
        if row.get('indexCode')!=code:raise ValueError('benchmark identity mismatch')
        day=datetime.strptime(row['tradeDate'],'%Y%m%d').date().isoformat()
        value=float(row['close'])
        if not math.isfinite(value) or value<=0:raise ValueError('invalid benchmark close')
        if day in by and by[day]!=value:raise ValueError('conflicting benchmark day')
        by[day]=value
    missing=sorted(set(days)-by.keys())
    if missing:raise ValueError('missing benchmark trading days: '+','.join(missing))
    ordered=sorted(set(days))
    if not ordered:raise ValueError('empty reference calendar')
    start=by[ordered[0]]
    return {'code':code,'basis':'official-gross-total-return','source_url':document['url'],
            'start':ordered[0],'end':ordered[-1],
            'excluded_dates':sorted(set(by)-set(ordered)),
            'rows':[{'date':day,'close':by[day],'index':by[day]/start} for day in ordered]}
