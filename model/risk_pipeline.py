"""当前筛选的总回报输入管线。只读本地PIT日线；不调用Baostock或修改下载。"""
import copy
import hashlib
import json
import os
import re
import threading
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path
from total_return import analyze,CoverageError

_CACHE={}
_LOCK=threading.Lock()


def calendar(as_of, loader):
    """两独立指数的日期交叉核对；进程内缓存，筛选线程共享。"""
    with _LOCK:
        key=(as_of,loader)
        if key in _CACHE:return _CACHE[key]
        day=date.fromisoformat(as_of);end=day.replace(day=1)-timedelta(days=1)
        begin=date(end.year-3,end.month,1)
        by_index={};sources=[]
        for code in ('sh000001','sz399001'):
            days=set()
            for year in range(begin.year,end.year+1):
                start=max(begin,date(year,1,1));stop=min(end,date(year,12,31))
                url=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,{start},{stop},640,qfq'
                response=loader(url,attempts=2)
                if response.get('code')!=0:raise CoverageError('calendar response error')
                rows=(response.get('data') or {}).get(code,{}).get('day',[])
                dates=[r[0] for r in rows if str(start)<=r[0]<=str(stop)]
                if len(dates)!=len(set(dates)):raise CoverageError('duplicate index date')
                if len(dates)<max(1,(stop-start).days//3):raise CoverageError('sparse index calendar')
                days.update(dates);sources.append({'url':url,'dates':dates})
            by_index[code]=days
        if by_index['sh000001']!=by_index['sz399001']:raise CoverageError('index calendars disagree')
        days=sorted(by_index['sh000001'])
        months={}
        for day in days:months.setdefault(day[:7],[]).append(day)
        if len(months)!=37:raise CoverageError('calendar lacks 37 months')
        start=max(months[min(months)]);finish=max(months[max(months)])
        result={'dates':[d for d in days if start<=d<=finish],'start':start,'end':finish,'sources':sources}
        _CACHE[key]=result
        return result


def parse_plan(text):
    """只接受结构明确的每N股送/转/派；配股、含糊文本直接拒绝。"""
    text=re.sub(r'\s+','',text or '')
    m=re.fullmatch(r'(\d+(?:\.\d+)?)(.*)',text)
    if not m or float(m[1])<=0:raise CoverageError('unrecognized corporate action: '+text)
    tail=m[2];tokens=re.findall(r'(送|转增|转|派)(\d+(?:\.\d+)?)(股|元)?',tail)
    consumed=''.join(a+b+c for a,b,c in tokens)
    if not tokens or consumed!=tail:raise CoverageError('unsupported corporate action: '+text)
    seen=set();cash=stocks=reserve=Decimal(0)
    for label,amount,unit in tokens:
        kind='转' if label=='转增' else label
        if kind in seen or (kind=='派' and unit=='股') or (kind!='派' and unit=='元'):
            raise CoverageError('ambiguous corporate action: '+text)
        seen.add(kind);value=Decimal(amount)/Decimal(m[1])
        if kind=='派':cash=value
        elif kind=='送':stocks=value
        else:reserve=value
    return {'dividCashPsBeforeTax':str(cash),'dividStocksPs':str(stocks),'dividReserveToStockPs':str(reserve)}


def action_rows(rows, code, as_of, start, end):
    result=[]
    for row in rows:
        day=(row.get('EX_DIVIDEND_DATE') or '')[:10]
        if row.get('ASSIGN_PROGRESS')!='实施方案' or not start<day<=end:continue
        notice=(row.get('NOTICE_DATE') or '')[:10]
        if not notice or not notice<=day or notice>as_of:raise CoverageError('invalid corporate action availability')
        if row.get('SECUCODE') and row['SECUCODE'][:6]!=code:raise CoverageError('wrong action security')
        result.append({'dividOperateDate':day,'dividPayDate':(row.get('PAY_CASH_DATE') or '')[:10],
                       'dividCashStock':row.get('IMPL_PLAN_PROFILE'),**parse_plan(row.get('IMPL_PLAN_PROFILE')),
                       'source':'eastmoney-RPT_F10_DIVIDEND_MAIN','announcement_date':notice})
    return result


def reconstruct(code,as_of,dividends,cal,root):
    sec=('sh.' if code.startswith('6') else 'sz.')+code
    path=Path(root)/(sec+'.json')
    raw=path.read_bytes();data=json.loads(raw)
    if data.get('code')!=sec:raise CoverageError('wrong local security')
    dates=[r['date'] for r in data['daily'] if cal['start']<=r['date']<=cal['end']]
    if sorted(dates)!=cal['dates']:raise CoverageError('daily data does not cover independent calendar')
    overlays=action_rows(dividends,code,as_of,cal['start'],cal['end'])
    data=copy.deepcopy(data);data.setdefault('dividend',[]).extend(overlays)
    calculation=analyze(data,cal['start'],cal['end'])
    series=calculation['series'];m=calculation['metrics'];monthly={}
    for r in series:monthly[r['date'][:7]]=r['index']
    return {'version':'action-return-v1','basis':calculation['assumption'],'status':'reconstructed',
            'as_of':as_of,'reference_date':cal['end'],'reference_close':series[-1]['index'],
            'high36':max(r['index'] for r in series),'closes':list(monthly.values()),
            'drawdown':m['current_drawdown'],'max_drawdown':m['max_drawdown'],'vol':m['vol'],
            'total_return':m['total_return'],'total_return_verified':False,'data_checks_passed':True,
            'reason':'cash/bonus model and input consistency checked; full issuer audit pending',
            'source':{'local_sha256':hashlib.sha256(raw).hexdigest(),'fetched':data.get('fetched'),
                      'calendar':cal,'overlays':overlays,'events':calculation['events'],
                      'daily':[r for r in data['daily'] if cal['start']<=r['date']<=cal['end']]}}


def current_risk(code,as_of,dividends,loader):
    root=Path(os.environ.get('STOCK_ANALYSIS_PIT_DIR',str(Path(__file__).resolve().parents[1]/'data/pit')))
    sec=('sh.' if code.startswith('6') else 'sz.')+code
    if not (root/(sec+'.json')).is_file():raise CoverageError('local unadjusted daily snapshot unavailable')
    return reconstruct(code,as_of,dividends,calendar(as_of,loader),root)
