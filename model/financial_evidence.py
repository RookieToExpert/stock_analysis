"""Dated issuer evidence for fields missing from the provider; never mutates raw data."""
from datetime import date
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from annual_supplements import field_value, verified_annual_version

ROOT=Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def default_ledger():
    return json.loads((ROOT/'model/verified_financials.json').read_text())


@lru_cache(maxsize=1)
def cash_by_period():
    by_period = {}
    for row in default_ledger():
        by_period.setdefault((row['code'], row['statDate']), []).append(row)
    return by_period


def balance_bound(code, statement_date, as_of):
    """An independently sourced lower bound may disprove, never prove, net cash."""
    ledger=json.loads((ROOT/'model/verified_balance_bounds.json').read_text())
    matches=[r for r in ledger if r['code']==code and r['statement_date']==statement_date
             and r['statement_date']<=r['available_date']<as_of]
    if len(matches)!=1:return None
    fix=matches[0]
    with gzip.open(ROOT/fix['source_text_path'],'rt',newline='') as f:text=f.read()
    if hashlib.sha256(text.encode()).hexdigest()!=fix['source_text_sha256']:return None
    return dict(fix)


def financing_evidence(code, start_year, end_year, as_of, ledger=None):
    if ledger is None:
        ledger=json.loads((ROOT/'model/verified_financing.json').read_text())
    try:
        when=date.fromisoformat(as_of)
        matches=[r for r in ledger if r['code']==code and r['start_year']==start_year
                 and r['end_year']==end_year and date.fromisoformat(r['available_date'])<when]
        if len(matches)!=1 or end_year-start_year!=4:return None
        fix=matches[0];annual=fix['annual_evidence']
        if sorted(r['statDate'] for r in annual)!=[f'{y}-12-31' for y in range(start_year,end_year+1)]:return None
        cash=noncash=Decimal(0)
        for proof in annual:
            if not date.fromisoformat(proof['statDate'])<=date.fromisoformat(proof['available_date'])<when:return None
            with gzip.open(ROOT/proof['source_text_path'],'rt',newline='') as f:text=f.read()
            if hashlib.sha256(text.encode()).hexdigest()!=proof['source_text_sha256']:return None
            annual_cash=Decimal(proof['parent_cash_equity_financing'])
            annual_noncash=Decimal(proof['noncash_issuance'])
            if not all(v.is_finite() and v>=0 for v in (annual_cash,annual_noncash)):return None
            cash+=annual_cash
            noncash+=annual_noncash
        if not (cash+noncash).is_finite() or cash<0 or noncash<0:return None
        if cash+noncash!=Decimal(str(fix['parent_equity_financing'])):return None
        if fix['available_date']!=max(r['available_date'] for r in annual):return None
        return dict(fix)
    except (ValueError,KeyError,TypeError,InvalidOperation,OSError):return None


def verified_operating_cash_flow(data, period, day, ledger=None):
    """Return an independently reported amount, not a fabricated CFO/NP ratio.

    A financial field match does not certify all fields or historical versions.
    Evidence is usable strictly after publication, like the PIT specification.
    """
    if ledger is None:
        ledger = cash_by_period().get((data.get('code'), period), [])
        if not ledger:
            visible = [r for r in data.get('fin', {}).get('cash', []) if r.get('statDate') == period
                       and r.get('pubDate') and r['pubDate'] < day]
            if len(visible) > 1 or any(r.get('CFOToNP') not in (None, '') for r in visible):
                return None
            version = verified_annual_version(data, period, day)
            amount = field_value(version, 'operating_cash_flow')
            if amount is None:
                return None
            proof = next(s for s in version['sources'] if s['facts'].get('operating_cash_flow') == str(amount))
            return {'amount': float(amount), 'evidence': proof}
    try:
        when=date.fromisoformat(day);end=date.fromisoformat(period)
        fixes=[r for r in ledger if r['code']==data.get('code') and r['statDate']==period
               and r['field']=='operating_cash_flow' and date.fromisoformat(r['available_date'])<when]
        if len(fixes)!=1:return None
        fix=fixes[0]
        if end>date.fromisoformat(fix['available_date']):return None
        rows={t:[r for r in data.get('fin',{}).get(t,[]) if r.get('statDate')==period
                 and r.get('pubDate') and date.fromisoformat(r['pubDate'])<when] for t in ('cash','profit')}
        if any(len(v)!=1 for v in rows.values()):return None
        cash,profit=rows['cash'][0],rows['profit'][0]
        if any(row.get('code', fix['code']) != fix['code'] for row in (cash, profit)):
            return None
        if (cash.get('CFOToNP') not in (None,'')
                or cash['pubDate']!=fix['expected_cash_pubDate']
                or profit['pubDate']!=fix['available_date']
                or Decimal(profit['netProfit'])!=Decimal(fix['expected_net_profit'])):return None
        amount=Decimal(fix['value'])
        if not amount.is_finite() or not fix.get('source'):return None
        if 'operating_cash_inflow' in fix or 'operating_cash_outflow' in fix:
            inflow = Decimal(fix['operating_cash_inflow'])
            outflow = Decimal(fix['operating_cash_outflow'])
            if not (inflow.is_finite() and outflow.is_finite() and inflow - outflow == amount):
                return None
        if fix.get('statement_basis')!='consolidated_cash_flow_statement_current_year_RMB_yuan':return None
        with gzip.open(ROOT/fix['source_text_path'],'rt',newline='') as f:text=f.read()
        if hashlib.sha256(text.encode()).hexdigest()!=fix['source_text_sha256']:return None
        return {'amount':float(amount),'evidence':fix}
    except (ValueError,KeyError,TypeError,InvalidOperation,OSError):
        return None
