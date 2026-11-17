"""Reconcile only exact six-decimal rounding of matching cross-source actions."""
import copy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

FIELDS=('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs')
SOURCE='eastmoney-RPT_F10_DIVIDEND_MAIN'


def reconcile_precision(snapshot):
    changes=[]
    for row in snapshot.get('dividend',[]):
        if row.get('source') or row.get('verified_action_source'):
            continue
        candidates=[r for r in snapshot['dividend'] if r.get('source')==SOURCE
                    and not r.get('verified_action_source')
                    and r.get('dividOperateDate')==row.get('dividOperateDate')]
        if len(candidates)!=1:continue
        other=candidates[0]
        try:
            low=[Decimal(row.get(k) or '0') for k in FIELDS]
            high=[Decimal(other.get(k) or '0') for k in FIELDS]
            if not all(v.is_finite() and v>=0 for v in low+high):continue
            if low==high:continue
            if any(a!=b.quantize(Decimal('.000001'),rounding=ROUND_HALF_UP) for a,b in zip(low,high)):
                continue
        except (InvalidOperation,TypeError,ValueError):continue
        changes.append({'original':copy.deepcopy(row),'higher_precision':copy.deepcopy(other),
                        'rule':'exact round-half-up to six decimal places; no price inference'})
        row.update({k:other.get(k) or '0' for k in FIELDS})
    return changes
