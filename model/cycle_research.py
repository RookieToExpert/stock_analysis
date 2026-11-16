#!/usr/bin/env python3
"""运行已登记的周期 FCF 截面对照，不改主模型、不读取未来收益。"""
import json,copy,sys
from pathlib import Path
from statistics import median
from collections import Counter
from recompute import read_lines
from score import evaluate
from rules import clean_years,score,grade
from report import split


def conservative_fcf(d):
    years=clean_years(d.get('years',[]))
    if len(years)!=5 or not d.get('mv') or d['mv']<=0:return None
    values=[]
    for row in years:
        from math import isfinite
        if any(not isinstance(row.get(k),(float,int)) or not isfinite(row[k]) for k in ('ocf','capex')):return None
        values.append(row['ocf']-row['capex'])
    return min(sum(values)/5,median(values),values[0])/d['mv']*100


def run(path):
    original=[];experiment=[];changes=[]
    for line in read_lines(path):
        d=json.loads(line);old=evaluate(d);new=copy.deepcopy(old)
        new['metrics']['fcf_yield']=conservative_fcf(d)
        new.update(score(new['metrics']))
        new['等级']=grade(new['总分'],new['排雷'],new['缺数据']+(['周期实验FCF未知'] if new['metrics']['fcf_yield'] is None else []))
        original.append(old);experiment.append(new)
        if new['总分']!=old['总分'] or new['等级']!=old['等级']:
            changes.append(dict(code=d['code'],name=d['name'],industry=d['industry'],old_score=old['总分'],new_score=new['总分'],old_grade=old['等级'],new_grade=new['等级'],old_fcf_yield=old['metrics']['fcf_yield'],new_fcf_yield=new['metrics']['fcf_yield']))
    a=split(original)[0];b=split(experiment)[0];sa={x['code'] for x in a};sb={x['code'] for x in b}
    return {'experiment':'CYCLE_RESEARCH_V1','validation':'in-sample cross-section; no return claim',
            'inputs':len(original),'baseline_main':len(a),'experimental_main':len(b),
            'intersection':len(sa&sb),'removed':sorted(sa-sb),'added':sorted(sb-sa),
            'baseline_industries':dict(Counter(x['industry'] for x in a)),
            'experimental_industries':dict(Counter(x['industry'] for x in b)),
            'changed_count':len(changes),'changes':changes}


if __name__=='__main__':
    output=run(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(output,ensure_ascii=False,indent=2))
    print({k:v for k,v in output.items() if k!='changes'})
