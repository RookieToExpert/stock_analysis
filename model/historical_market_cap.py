"""PIT-spec market-cap proxy: prior raw close times latest published total shares.

This implements the stated v1.1 proxy, not an independently certified effective
share register. Corporate actions after the report can change actual shares.
"""
from datetime import date
from decimal import Decimal, InvalidOperation


def calculate(data, day):
    try:
        when=date.fromisoformat(day)
        reports=[]
        for row in data.get('fin',{}).get('profit',[]):
            pub=date.fromisoformat(row['pubDate']);period=date.fromisoformat(row['statDate'])
            if pub<when:
                if period>pub:return None
                reports.append(row)
        if not reports:return None
        latest=max(r['statDate'] for r in reports)
        selected=[r for r in reports if r['statDate']==latest]
        if len(selected)!=1:return None
        report=selected[0]
        if report.get('code',data.get('code'))!=data.get('code'):return None
        if isinstance(report['totalShare'],bool):return None
        shares=Decimal(report['totalShare'])
        prices=[r for r in data.get('daily',[]) if date.fromisoformat(r['date'])<when]
        if not prices:return None
        price_day=max(r['date'] for r in prices)
        rows=[r for r in prices if r['date']==price_day]
        if len(rows)!=1:return None
        if isinstance(rows[0]['close'],bool):return None
        close=Decimal(rows[0]['close'])
        if not shares.is_finite() or not close.is_finite() or shares<=0 or close<=0:return None
        return {'value_yuan':float(shares*close),'shares':str(shares),'close':str(close),
                'price_date':price_day,'statement_date':report['statDate'],'publication_date':report['pubDate'],
                'basis':'v1.1 latest published reported shares times prior unadjusted close',
                'effective_share_register_verified':False,'unrestated_vintage_verified':False}
    except (KeyError,TypeError,ValueError,InvalidOperation):return None
