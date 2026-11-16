"""税前总回报研究序列：除息日收盘按现金权利再投资，允许碎股，无税费。
仅支持现金分红与送转；配股等未建模事件拒绝。不等于实际到账可交易组合。
"""
import math
from datetime import date
from statistics import stdev


class CoverageError(ValueError):
    pass


def number(value, label):
    if isinstance(value, bool):
        raise CoverageError('boolean '+label)
    try:
        x=float(value)
    except (ValueError,TypeError):
        raise CoverageError('invalid '+label)
    if not math.isfinite(x):
        raise CoverageError('nonfinite '+label)
    return x


def redundant_adjustment_dates(snapshot, events):
    """仅识别已知事件之后、前后复权累计因子均未变化的重复记录。"""
    ignored = []
    previous = None
    anchored = False
    for row in sorted(snapshot.get('adjust', []), key=lambda r: r.get('dividOperateDate', '')):
        day = row.get('dividOperateDate', '')
        factors = []
        for field in ('foreAdjustFactor', 'backAdjustFactor'):
            try:
                value = number(row.get(field), field)
                factors.append(value if value > 0 else None)
            except CoverageError:
                factors.append(None)
        unchanged = (previous is not None and day > previous[0]
                     and None not in factors and factors == previous[1])
        if day in events:
            anchored = True
        elif anchored and unchanged:
            ignored.append(day)
        else:
            anchored = False
        previous = (day, factors)
    return ignored


def events_from_snapshot(snapshot, start, end):
    events={}
    for r in snapshot.get('dividend',[]):
        day=r.get('dividOperateDate','')
        if not start < day <= end:
            continue
        text=r.get('dividCashStock','')
        if '配股' in text or ('配' in text and '派' not in text):
            raise CoverageError('unsupported rights event '+day)
        def value(field, marker):
            v=r.get(field)
            if v in ('',None):
                if marker in text:
                    raise CoverageError('missing '+field+' '+day)
                return 0.
            n=number(v,field)
            if n<0: raise CoverageError('negative corporate action '+day)
            return n
        e={'cash':value('dividCashPsBeforeTax','派'),
           'shares':value('dividStocksPs','送')+value('dividReserveToStockPs','转')}
        if day in events and events[day]!=e:
            raise CoverageError('conflicting events '+day)
        events[day]=e
    redundant = set(redundant_adjustment_dates(snapshot, events))
    for r in snapshot.get('adjust',[]):
        day=r.get('dividOperateDate','')
        if start < day <= end and day not in events and day not in redundant:
            raise CoverageError('adjustment without corporate action '+day)
    return events


def build(daily, events, start, end):
    date.fromisoformat(start);date.fromisoformat(end)
    rows=sorted((r for r in daily if start<=r['date']<=end),key=lambda r:r['date'])
    if len(rows)<2 or rows[0]['date']!=start or rows[-1]['date']!=end:
        raise CoverageError('missing boundary trading day')
    if len({r['date'] for r in rows})!=len(rows):
        raise CoverageError('duplicate trading day')
    if set(events)-{r['date'] for r in rows[1:]}:
        raise CoverageError('corporate action outside observed trading days')
    previous=number(rows[0]['close'],'close')
    if previous<=0: raise CoverageError('nonpositive price')
    wealth=1.;out=[{'date':start,'index':wealth}]
    for r in rows[1:]:
        close=number(r['close'],'close');reference=number(r['preclose'],'preclose')
        if close<=0 or reference<=0: raise CoverageError('nonpositive price '+r['date'])
        e=events.get(r['date'],{'cash':0.,'shares':0.})
        cash=number(e['cash'],'cash');shares=number(e['shares'],'shares')
        if cash<0 or shares<0: raise CoverageError('unsupported negative action')
        expected=(previous-cash)/(1+shares)
        # 交易所参考价以分舍入；留 1.1 分容差，不靠收益曲线猜缺失分红。
        if expected<=0 or abs(expected-reference)>0.011:
            raise CoverageError('unexplained reference price '+r['date'])
        wealth *= (close*(1+shares)+cash)/previous
        if not math.isfinite(wealth): raise CoverageError('nonfinite wealth')
        out.append({'date':r['date'],'index':wealth})
        previous=close
    return out


def risk(series):
    months={}
    peak=series[0]['index'];mdd=0.
    for r in series:
        peak=max(peak,r['index']);mdd=max(mdd,1-r['index']/peak)
        months[r['date'][:7]]=r['index']
    keys=sorted(months)
    ids=[int(k[:4])*12+int(k[5:]) for k in keys]
    if len(keys)!=37 or any(b-a!=1 for a,b in zip(ids,ids[1:])):
        raise CoverageError('need 37 consecutive month endpoints')
    returns=[months[b]/months[a]-1 for a,b in zip(keys,keys[1:])]
    return {'current_drawdown':(1-series[-1]['index']/peak)*100,
            'max_drawdown':mdd*100,'vol':stdev(returns)*12**.5*100,
            'total_return':(series[-1]['index']/series[0]['index']-1)*100}


def analyze(snapshot, start, end):
    events=events_from_snapshot(snapshot,start,end)
    series=build(snapshot['daily'],events,start,end)
    return {'assumption':'gross-ex-date-close-reinvestment-v1','start':start,'end':end,
            'events':events,'series':series,'metrics':risk(series),
            'redundant_adjustment_dates':[d for d in redundant_adjustment_dates(snapshot,events) if start<d<=end],
            'validation':'internal consistency only; official announcement audit required'}
