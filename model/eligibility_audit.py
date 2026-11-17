#!/usr/bin/env python3
"""只读复核上市年限/ST资格后的年报覆盖。行业/市值过滤未知则不宣称正式门槛通过。"""
import json,sys
import gzip,hashlib
from functools import lru_cache
from datetime import date
from pathlib import Path
from pit_audit import annual_missing
from historical_industry import lookup as industry_at
from historical_market_cap import calculate as market_cap_at


@lru_cache(maxsize=1)
def release_ledger():
    return json.loads(Path(__file__).with_name('verified_st_releases.json').read_text())


def verified_release(code, effective):
    matches=[r for r in release_ledger() if r['code']==code and r['effective_date']==effective]
    if len(matches)!=1:return {}
    proof=matches[0]
    try:
        with gzip.open(Path(__file__).resolve().parents[1]/proof['source_text_path'],'rt',newline='') as f:text=f.read()
        if hashlib.sha256(text.encode()).hexdigest()!=proof['source_text_sha256']:return {}
    except (OSError,ValueError):return {}
    return proof


def eligibility(data, day):
    basic=data.get('basic') or []
    if len(basic)!=1:return None,'basic_missing_or_ambiguous'
    try:
        ipo=date.fromisoformat(basic[0]['ipoDate']);when=date.fromisoformat(day)
    except (ValueError,KeyError,TypeError):return None,'ipo_unknown'
    age=when.year-ipo.year-((when.month,when.day)<(ipo.month,ipo.day))
    if age<5:return False,'listed_under_5_years'
    out=basic[0].get('outDate')
    if out and out<=day:return None,'universe_conflicts_with_delisting'
    rows=[r for r in data.get('daily',[]) if r.get('date')==day]
    if len(rows)!=1 or rows[0].get('isST') not in ('0','1'):return None,'evaluation_day_ST_unknown'
    if rows[0]['isST']=='1':return False,'ST'
    # A 1 -> 0 flag also occurs during delisting. It is not proof of ST release.
    history=sorted((r for r in data.get('daily',[]) if r.get('date','')<=day),key=lambda r:r['date'])
    last_st=max((r['date'] for r in history if r.get('isST')=='1'),default=None)
    if last_st:
        releases=[r['date'] for r in history if r['date']>last_st and r.get('isST')=='0']
        effective=min(releases)
        proof=data.get('st_release_verification') or verified_release(data.get('code'),effective)
        try:
            available=date.fromisoformat(proof.get('available_date',''))
            valid=(proof.get('source') and proof.get('effective_date')==effective
                   and available<=date.fromisoformat(effective)
                   and proof.get('status')=='normal_listing')
        except (ValueError,TypeError):valid=False
        if not valid:return None,'ST_release_requires_issuer_evidence'
    return True,'age_ST_pass'


def audit(root):
    universe=json.loads((root/'universe.json').read_text());members={}
    result={d:dict(universe=len(set(cs)),excluded=[],unknown_eligibility=[],eligible_annual_missing=[],eligible_complete=[],known_age_ST_eligible=0,market_cap_proxies={}) for d,cs in universe.items()}
    for day,codes in universe.items():
        for c in set(codes):members.setdefault(c,[]).append(day)
    for code,days in members.items():
        try:
            d=json.loads((root/(code+'.json')).read_text())
            if d.get('code')!=code:raise ValueError('code mismatch')
        except (OSError,ValueError) as exc:
            for day in days:result[day]['unknown_eligibility'].append({'code':code,'reason':'file_missing_or_invalid'})
            continue
        for day in days:
            eligible,reason=eligibility(d,day);entry=result[day]
            if eligible is None:entry['unknown_eligibility'].append({'code':code,'reason':reason})
            elif not eligible:entry['excluded'].append({'code':code,'reason':reason})
            else:
                entry['known_age_ST_eligible']+=1
                industry=industry_at(code,day)
                if industry is None:
                    entry['unknown_eligibility'].append({'code':code,'reason':'historical_industry_missing_or_ambiguous'})
                    continue
                if industry['financial']:
                    entry['excluded'].append({'code':code,'reason':'financial_industry_as_published','industry':industry})
                    continue
                entry['market_cap_proxies'][code]=market_cap_at(d,day)
                missing=annual_missing(d,day)
                if missing:entry['eligible_annual_missing'].append({'code':code,'reasons':missing})
                else:entry['eligible_complete'].append(code)
    for day,entry in result.items():
        n=len(entry['eligible_annual_missing'])+len(entry['eligible_complete'])
        entry['known_age_ST_industry_eligible']=n
        entry['industry_reference']=industry_at('000001',day)
        entry['market_cap_proxy_at_least_20bn']=sum(1 for r in entry['market_cap_proxies'].values() if r and r['value_yuan']>=20_000_000_000)
        entry['market_cap_proxy_unknown']=sum(r is None for r in entry['market_cap_proxies'].values())
        entry['missing_fraction_among_known_eligible']=len(entry['eligible_annual_missing'])/n if n else None
    return {'scope':'IPO age, evidence-backed ST release and latest published official industry; market-cap cut not yet certified',
            'strategy_gate_pass':False,'evaluations':result}


if __name__=='__main__':
    output=audit(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(output,ensure_ascii=False))
    for day,e in sorted(output['evaluations'].items()):
        print(day,'age_ST_industry_eligible',e['known_age_ST_industry_eligible'],'annual_missing',len(e['eligible_annual_missing']),
              'eligibility_unknown',len(e['unknown_eligibility']))
