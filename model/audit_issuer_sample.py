"""Reproduce the bounded issuer sample audit from archived sources, offline.

Checks explicitly reviewed net-profit values and cash-event evidence. It does
not certify five-year financing completeness, zero dividends from blank cells,
or an unbiased sample of the complete historical universe.
"""
import argparse
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import re
from extract_action_evidence import ex_date_matches


def read_text(root, key, meta):
    with gzip.open(root/(key+'.txt.gz'),'rt',newline='') as f:text=f.read()
    if hashlib.sha256(text.encode()).hexdigest()!=meta['text_sha256']:
        raise ValueError('source text hash mismatch: '+key)
    return text


def audit(reviews, reports, announcements):
    inputs={r['code']:r for r in json.loads((reports/'sample-input.json').read_text())}
    output=[]
    for review in json.loads(reviews.read_text()):
        code=review['code'];key=code+'-'+review['statDate']+('-original' if code=='sh.600687' else '')
        meta=json.loads((reports/(key+'.json')).read_text())
        text=read_text(reports,key,meta);compact=re.sub(r'\s+',' ',text)
        value=format(Decimal(review['consolidated_netProfit']),',.2f')
        pos=compact.find(value)
        if pos<0:raise ValueError('reviewed net-profit number absent: '+code)
        date_match=re.search(r'公告日期[:：]\s*(\d{4}-\d{2}-\d{2})',text)
        url_date=re.search(r'/finalpage/(\d{4}-\d{2}-\d{2})/',meta['source'])
        publication=(date_match or url_date)
        pub=publication[1] if publication else None
        if pub is None and meta.get('publication_evidence'):
            entry=meta['publication_evidence']['row']
            if (entry['art_code'] not in meta['source']
                    or code[3:] not in {c['stock_code'] for c in entry['codes']}):
                raise ValueError('publication evidence security/source mismatch')
            pub=entry['notice_date'][:10]
        events=[]
        for raw in inputs[code]['dividend']:
            day=raw['dividOperateDate'];cash=Decimal(raw.get('dividCashPsBeforeTax') or '0')
            if cash==0:continue
            docs=json.loads((announcements/(code+'-'+day+'.json')).read_text())['documents']
            matched=[]
            for doc in docs:
                s=re.sub(r'\s+','',read_text(announcements,doc['article'],doc))
                s=s.translate(str.maketrans({'（':'(', '）':')'}))
                if not ex_date_matches(s,day) or code[3:] not in s[:500] or doc['available_date']>day:continue
                actual={Decimal(x) for x in re.findall(r'每股现金红利(\d+(?:\.\d+)?)',s[:1000])}
                actual.update(Decimal(x)/10 for x in re.findall(r'每10股(?:派发)?现金(?:红利|分红)?(\d+(?:\.\d+)?)',s[:3000]))
                if cash in actual:matched.append(doc)
            if not matched:raise ValueError('cash event lacks matching issuer evidence: '+code+' '+day)
            events.append(dict(ex_date=day,cash=str(cash),status='matches',evidence=matched))
        marker=compact.find('应付普通股股利')
        output.append(dict(code=code,statDate=review['statDate'],source=meta['source'],
            source_text_sha256=meta['text_sha256'],supplier_pubDate=review['supplier_pubDate'],
            publication_date=pub,publication_check=('matches' if pub==review['supplier_pubDate'] else 'not_independently_dated'),
            net_profit='matches_reviewed_original_report',net_profit_excerpt=compact[max(0,pos-100):pos+len(value)+100],
            dividend_events=events,dividend_review=('implemented_events_match' if events else 'no_supplier_event_consistent_with_appropriation_note_not_zero_certified'),
            appropriation_excerpt=compact[max(0,marker-100):marker+240] if marker>=0 else None,
            complete_financing_and_debt_certified=False,
            financing_reason='Single annual report cannot establish complete five-year parent issuance including noncash dilution; blank perpetual/restricted-cash cells are not proof of zero.'))
    return dict(rows=output,net_profit_matches=len(output),implemented_cash_events=sum(len(r['dividend_events']) for r in output),
                formal_gate_passed=False,sample_basis='fixed partial-download sample; not complete-universe random sample')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reviews','reports','announcements','output'):p.add_argument(key,type=Path)
    a=p.parse_args();result=audit(a.reviews,a.reports,a.announcements)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))
