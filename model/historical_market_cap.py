"""PIT-spec market-cap proxy: prior raw close times latest published total shares.

This implements the stated v1.1 proxy, not an independently certified effective
share register. Corporate actions after the report can change actual shares.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from annual_supplements import effective_publication_date, field_value, later_reported_shares, verified_annual_version


def calculate(data, day):
    try:
        when=date.fromisoformat(day)
        reports=[]
        for row in data.get('fin',{}).get('profit',[]):
            pub=date.fromisoformat(effective_publication_date(data.get('code'), row['statDate'], row['pubDate']))
            period=date.fromisoformat(row['statDate'])
            if pub<when:
                if period>date.fromisoformat(row['pubDate']):return None
                reports.append(row)
        latest=max((r['statDate'] for r in reports), default='')
        later = later_reported_shares(data, day, latest)
        if later:
            latest, published, shares = later
        else:
            selected=[r for r in reports if r['statDate']==latest]
            if len(selected)!=1:return None
            report=selected[0]
            if report.get('code',data.get('code'))!=data.get('code'):return None
            published = effective_publication_date(data.get('code'), latest, report['pubDate'])
            value = report.get('totalShare')
            if value in (None, ''):
                version = verified_annual_version(data, latest, day)
                shares = field_value(version, 'totalShare')
                if shares is None:return None
                published = max(published, version['available_date'])
            else:
                if isinstance(value,bool):return None
                shares=Decimal(value)
        prices=[r for r in data.get('daily',[]) if date.fromisoformat(r['date'])<when]
        if not prices:return None
        price_day=max(r['date'] for r in prices)
        rows=[r for r in prices if r['date']==price_day]
        if len(rows)!=1:return None
        if isinstance(rows[0]['close'],bool):return None
        close=Decimal(rows[0]['close'])
        if not shares.is_finite() or not close.is_finite() or shares<=0 or close<=0:return None
        return {'value_yuan':float(shares*close),'shares':str(shares),'close':str(close),
                'price_date':price_day,'statement_date':latest,'publication_date':published,
                'basis':'v1.1 latest published reported shares times prior unadjusted close',
                'effective_share_register_verified':False,'unrestated_vintage_verified':False}
    except (KeyError,TypeError,ValueError,InvalidOperation):return None
