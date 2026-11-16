#!/usr/bin/env python3
"""只读复核上市年限/ST资格后的年报覆盖。行业/市值过滤未知则不宣称正式门槛通过。"""
import json,sys
from datetime import date
from pathlib import Path
from pit_audit import annual_missing


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
    return True,'age_ST_pass'


def audit(root):
    universe=json.loads((root/'universe.json').read_text());members={}
    result={d:dict(universe=len(set(cs)),excluded=[],unknown_eligibility=[],eligible_annual_missing=[],eligible_complete=[]) for d,cs in universe.items()}
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
                missing=annual_missing(d,day)
                if missing:entry['eligible_annual_missing'].append({'code':code,'reasons':missing})
                else:entry['eligible_complete'].append(code)
    for entry in result.values():
        n=len(entry['eligible_annual_missing'])+len(entry['eligible_complete'])
        entry['known_age_ST_eligible']=n
        entry['missing_fraction_among_known_eligible']=len(entry['eligible_annual_missing'])/n if n else None
    return {'scope':'IPO age and ST only; industry and market-cap cut not yet certified',
            'strategy_gate_pass':False,'evaluations':result}


if __name__=='__main__':
    output=audit(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(output,ensure_ascii=False))
    for day,e in sorted(output['evaluations'].items()):
        print(day,'eligible',e['known_age_ST_eligible'],'annual_missing',len(e['eligible_annual_missing']),
              'eligibility_unknown',len(e['unknown_eligibility']))
