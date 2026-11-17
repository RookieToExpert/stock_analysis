"""Strict mechanical extraction of issuer-announced differential distribution formulas.

Returns evidence candidates only. A full-window replay and review must precede ledger use.
Never derives a dividend or a reference adjustment from market prices.
"""
import re
import json
import gzip
import hashlib
from pathlib import Path
from decimal import Decimal
from datetime import date

num=r'(\d+(?:\.\d+)?)'
prev=r'(?:前(?:一交易日)?|股权登记日(?:股票)?)收盘价(?:格)?'


def ex_date_matches(text, day):
    """Match the explicit ex-date or the second date in the initial A-share table."""
    token=r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?(?=20\d{2}[年/-]|[^\d]|$)'
    def iso(groups):
        return date(*map(int,groups)).isoformat()
    for match in re.finditer(r'(?:除息|除权(?:除息|\(息\))?)日(?:及现金红利发放日)?(?:为)?[:：]?'+token,text):
        if iso(match.groups())==day:return True
    if '相关日期' in text:
        table=text.split('相关日期',1)[1][:450]
        dates=re.findall(token,table)
        if len(dates)>=2 and iso(dates[1])==day:return True
    return False


def extract(text, doc, code, day, row):
    date.fromisoformat(day)
    if date.fromisoformat(doc['available_date'])>date.fromisoformat(day):return None
    if hashlib.sha256(text.encode()).hexdigest()!=doc['text_sha256']:
        raise ValueError('announcement text hash mismatch')
    cash=Decimal(row.get('dividCashPsBeforeTax') or '0')
    shares=sum(Decimal(row.get(k) or '0') for k in ('dividStocksPs','dividReserveToStockPs'))
    if not all(v.is_finite() and v>=0 for v in (cash,shares)):return None
    s=re.sub(r'\s+','',text).translate(str.maketrans({'（':'(', '）':')','－':'-','﹣':'-','−':'-','一':'一','＋':'+','＝':'='}))
    if code[3:] not in s[:500] or not ex_date_matches(s,day):return None
    matches=list(re.finditer(prev+r'[-一]'+num+r'(?:元/股)?\)(?:÷|/)(?:\(1\+'+num+r'(?:股)?\)|'+num+r')',s))
    pairs={(Decimal(x[1]),Decimal(x[2]) if x[2] is not None else Decimal(x[3])-1) for x in matches}
    if not pairs and shares==0:
     xs=list(re.finditer(prev+r'[-一]'+num,s));pairs={(Decimal(x[1]),Decimal(0)) for x in xs};matches=xs
    if not pairs and cash==0:
     xs=list(re.finditer(prev+r'(?:÷|/)\(1\+'+num+r'\)',s));pairs={(Decimal(0),Decimal(x[1])) for x in xs};matches=xs
    if len(pairs)!=1:return None
    rc,rs=pairs.pop()
    actual_cash={Decimal(x) for x in re.findall(r'每股(?:派发)?(?:现金红利|派现|现金股利)(?:人民币)?'+num,s[:3000])}
    actual_shares={Decimal(x) for x in re.findall(r'每股(?:以资本公积金)?(?:转增(?:股份|股本)?|派送红股|送红股)'+num,s[:3000])}
    actual_cash.update(Decimal(x)/10 for x in re.findall(r'每10股(?:派发|派)?(?:现金|红利|股利|人民币)*'+num,s[:3000]))
    actual_shares.update(Decimal(x)/10 for x in re.findall(r'每10股(?:转增|派送红股|送红股)'+num,s[:3000]))
    cash_ok=cash in actual_cash or cash==0 and rc==0 and not actual_cash and shares>0
    shares_ok=shares in actual_shares or shares==0 and rs==0 and not actual_shares
    if not cash_ok or not shares_ok:return None
    if not 0<=rc<=cash or not 0<=rs<=shares:return None
    expr=matches[-1][0]
    return dict(code=code,ex_date=day,available_date=doc['available_date'],expected_cash=[str(cash)],cash=str(cash),shares=str(shares),reference_cash=str(rc),reference_shares=str(rs),source=doc['source'],source_pdf_sha256=doc['pdf_sha256'],source_text_sha256=doc['text_sha256'],reference_expression=expr,reason='发行人实施公告：回购账户不参与分配，实际持有人权益与公告除权参考口径分开')
