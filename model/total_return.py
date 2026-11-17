"""税前总回报研究序列：除息日收盘按现金权利再投资，允许碎股，无税费。
支持公告核验的分红送转、重整及停牌缴款期间价格不变的配股研究模型。
其他配股拒绝；配股外部认购资金按时间加权单位化剔除，待上市股份不视为可交易。
不等于实际到账可交易组合。
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


def redundant_adjustment_dates(snapshot, events, start=None):
    """仅识别已知事件之后、前后复权累计因子均未变化的重复记录。"""
    ignored = []
    previous = None
    anchored = False
    anchors=set(events)
    # 起点已是除权后的收盘价，不再领一次分红，但该日仍能锚定随后重复的因子。
    if start and any(r.get('dividOperateDate')==start for r in snapshot.get('dividend',[])):
        anchors.add(start)
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
        if day in anchors:
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
        if ('配股' in text or ('配' in text and '派' not in text)) and not ('rights_shares' in r and r.get('verified_action_source')):
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
        # 差异化分派：实际持有人权益用于收益，公告虚拟权益仅用于校验除权参考价。
        for field in ('reference_cash','reference_shares','announced_reference_price','announced_previous_close',
                      'rights_shares','rights_price','reference_rights_shares'):
            if field in r:
                if not r.get('verified_action_source'):
                    raise CoverageError('reference action lacks verified source '+day)
                e[field]=number(r[field],field)
                if e[field]<0:raise CoverageError('negative reference action '+day)
        if any(k in e for k in ('rights_shares','rights_price','reference_rights_shares')):
            if not all(e.get(k,0)>0 for k in ('rights_shares','rights_price','reference_rights_shares')):
                raise CoverageError('incomplete paid rights '+day)
        if day in events and events[day]!=e:
            raise CoverageError('conflicting events '+day)
        events[day]=e
    redundant = set(redundant_adjustment_dates(snapshot, events, start))
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
        ref_cash=number(e.get('reference_cash',cash),'reference cash')
        ref_shares=number(e.get('reference_shares',shares),'reference shares')
        if ref_cash<0 or ref_shares<0:raise CoverageError('negative reference action')
        expected=(previous-ref_cash)/(1+ref_shares)
        rights=number(e.get('rights_shares',0),'rights shares')
        price=number(e.get('rights_price',0),'rights price')
        ref_rights=number(e.get('reference_rights_shares',0),'reference rights shares')
        if rights:
            if price<=0 or ref_rights<=0 or ref_rights>rights or cash or shares:
                raise CoverageError('unsupported paid rights combination')
            expected=(previous+ref_rights*price)/(1+ref_rights)
        # 重整转增可能全部分给债权人；公告确定的参考价不等于持有人收益。
        # 仅接受同一事件的公告价与其前收盘锚点，不能从供应商 preclose 反推。
        if 'announced_reference_price' in e or 'announced_previous_close' in e:
            if not all(k in e for k in ('announced_reference_price','announced_previous_close')):
                raise CoverageError('incomplete announced reference '+r['date'])
            anchor=number(e['announced_previous_close'],'announced previous close')
            if anchor<=0 or abs(previous-anchor)>0.000001:
                raise CoverageError('announced previous close mismatch '+r['date'])
            expected=number(e['announced_reference_price'],'announced reference price')
        # 交易所参考价以分舍入；留 1.1 分容差，不靠收益曲线猜缺失分红。
        if expected<=0 or abs(expected-reference)>0.011:
            raise CoverageError('unexplained reference price '+r['date'])
        # Time-weighted normalization removes paid subscription capital. This
        # does not assume that newly allocated shares can already be sold.
        wealth *= (close*(1+shares+rights)+cash)/(previous+rights*price)
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
    basis=('gross-reinvestment-funded-rights-unitized-v2' if any(e.get('rights_shares') for e in events.values())
           else 'gross-ex-date-close-reinvestment-v1')
    return {'assumption':basis,'start':start,'end':end,
            'events':events,'series':series,'metrics':risk(series),
            'redundant_adjustment_dates':[d for d in redundant_adjustment_dates(snapshot,events,start) if start<d<=end],
            'validation':'internal consistency only; official announcement audit required'}
