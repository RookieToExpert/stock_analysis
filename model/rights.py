"""Verified paid-rights events; funding is never credited as investment income."""
import copy
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from total_return import CoverageError


def validate(event):
    fields=('offer_available_date','record_date','payment_start','payment_end','ex_date','listing_date')
    dates=[date.fromisoformat(event[k]) for k in fields]
    if dates!=sorted(dates) or dates[1]>=dates[2] or dates[3]>=dates[4]:
        raise ValueError('invalid rights chronology')
    available=date.fromisoformat(event['available_date'])
    listing_available=date.fromisoformat(event['listing_available_date'])
    if not dates[3]<=available<=dates[4] or not dates[4]<=listing_available<=dates[5]:
        raise ValueError('invalid rights evidence chronology')
    for field in ('subscription_price','offered_shares_per_share','issued_shares_per_share'):
        try:value=Decimal(event[field])
        except (InvalidOperation,TypeError) as exc:raise ValueError('invalid rights amount') from exc
        if not value.is_finite() or value<=0:raise ValueError('invalid rights amount')
    if Decimal(event['issued_shares_per_share'])>Decimal(event['offered_shares_per_share']):
        raise ValueError('issued rights exceed offer')
    if not all(event.get(k) for k in ('source','offer_source','listing_source')):
        raise ValueError('rights source missing')


def apply_verified_rights(snapshot, as_of, start, end, ledger=None):
    if ledger is None:
        ledger=json.loads(Path(__file__).with_name('verified_rights.json').read_text())
    changes=[]
    for event in ledger:
        if event['code']!=snapshot.get('code') or event['available_date']>as_of:continue
        if not start<event['ex_date']<=end:continue
        validate(event)
        # This time-weighted research approximation is valid only if the entire
        # subscription interval has no trading/price movement. Otherwise reject.
        if start>event['record_date']:raise CoverageError('rights window starts after record date')
        rows=[r for r in snapshot['daily'] if event['record_date']<=r['date']<event['ex_date']]
        rows.sort(key=lambda r:r['date'])
        if not rows or rows[0]['date']!=event['record_date'] or len(rows)<2:
            raise CoverageError('rights subscription coverage missing')
        anchor=Decimal(rows[0]['close'])
        if any(r.get('tradestatus')!='0' or Decimal(r['close'])!=anchor for r in rows[1:]):
            raise CoverageError('rights funding interval requires daily cash-flow model')
        row=dict(dividOperateDate=event['ex_date'],dividCashPsBeforeTax='0',dividStocksPs='0',
                 dividReserveToStockPs='0',dividCashStock='公告核验付费配股',
                 verified_action_source=event['source'],rights_shares=event['offered_shares_per_share'],
                 rights_price=event['subscription_price'],reference_rights_shares=event['issued_shares_per_share'])
        existing=[r for r in snapshot.get('dividend',[]) if r.get('dividOperateDate')==event['ex_date']]
        if existing:
            if existing==[row]:continue
            raise CoverageError('rights source changed or combined event unsupported')
        snapshot.setdefault('dividend',[]).append(row)
        changes.append(copy.deepcopy(event))
    return changes
