"""Select report years usable while the sampled company was still listed."""
from datetime import date


def latest_listed_annual(data, as_of, period_ceiling):
    when=date.fromisoformat(as_of);ceiling=date.fromisoformat(period_ceiling)
    basics=data.get('basic') or []
    if len(basics)!=1:raise ValueError('ambiguous listing history')
    ipo=date.fromisoformat(basics[0]['ipoDate'])
    out=date.fromisoformat(basics[0]['outDate']) if basics[0].get('outDate') else when
    candidates=[]
    for row in data.get('fin',{}).get('profit',[]):
        try:
            period=date.fromisoformat(row['statDate']);pub=date.fromisoformat(row['pubDate'])
        except (KeyError,TypeError,ValueError):continue
        if period.month==12 and period.day==31 and period<=ceiling and period<=pub and ipo<=pub<min(out,when):
            candidates.append(row)
    if not candidates:return None
    newest=max(r['statDate'] for r in candidates)
    matches=[r for r in candidates if r['statDate']==newest]
    if len(matches)!=1:raise ValueError('ambiguous financial vintage')
    return dict(matches[0])
