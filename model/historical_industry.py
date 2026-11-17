"""Official published industry classifications, selected by publication date.

Quarter/half-year labels are observation periods, never availability dates.
Missing or contradictory security rows remain unknown; no current-data fallback.
"""
import argparse
from datetime import date
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]/'results/industry-sources-2026-11-17'


def parse_table(text, by_stock=False):
    rows={};conflicts={};current=None;parsed_rows=0
    for line in text.splitlines():
        stock=re.search(r'(?<!\d)(\d{6})(?!\d)',line)
        if not stock:continue
        code=stock[1]
        if by_stock:
            if line[:stock.start()].strip():raise ValueError('stock-sorted row starts with unexpected columns')
            category=re.search(r'\s([A-S])\s',line[stock.end():])
            majors=re.findall(r'(?<!\d)(\d{2})(?!\d)',line[stock.end():])
            if not category or not majors:raise ValueError('incomplete industry row: '+line)
            major=majors[-1];sector=category[1]
        else:
            prefix=line[:stock.start()]
            major_match=re.search(r'(?<!\d)(\d{2})(?!\d)',prefix)
            if major_match:current=major_match[1]
            if current is None:raise ValueError('industry row precedes group header')
            major=current;sector=None
        row={'major':major,'sector':sector,'financial':sector=='J' if by_stock else major in ('66','67','68','69')}
        parsed_rows+=1
        if code in rows:
            conflicts.setdefault(code,[rows[code]]).append(row)
        else:rows[code]=row
    for code in conflicts:rows.pop(code,None)
    return {'rows':rows,'ambiguous_codes':conflicts,'parsed_rows':parsed_rows}


def build(root):
    manifest=[]
    for path in sorted(root.glob('20*.json')):
        meta=json.loads(path.read_text())
        if not meta.get('complete'):continue
        documents=meta['documents']
        by_stock=meta['taxonomy']=='CAPCO2023'
        if by_stock:
            documents=[d for d in documents if '股票代码' in d.get('label','')]
        if len(documents)!=1:raise ValueError('ambiguous industry attachment: '+str(path))
        doc=documents[0]
        with gzip.open(root/(doc['key']+'.txt.gz'),'rt',newline='') as f:text=f.read()
        if hashlib.sha256(text.encode()).hexdigest()!=doc['text_sha256']:raise ValueError('industry source hash changed')
        result=parse_table(text,by_stock)
        if len(result['rows'])<2500:raise ValueError('industry source incomplete: '+str(path))
        entry={k:meta[k] for k in ('period','available_date','taxonomy','page')}
        entry.update(source=doc['source'],text_sha256=doc['text_sha256'],row_count=len(result['rows']),
                     ambiguous_codes=result['ambiguous_codes'],parsed_rows=result['parsed_rows'])
        filename=meta['period']+'-classification.json.gz'
        with gzip.open(root/filename,'wt') as f:json.dump(result['rows'],f,ensure_ascii=False)
        entry['file']=filename;entry['classification_sha256']=hashlib.sha256((root/filename).read_bytes()).hexdigest()
        manifest.append(entry)
    manifest.sort(key=lambda r:r['available_date'])
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


@lru_cache(maxsize=1)
def manifest():
    return json.loads((ROOT/'manifest.json').read_text())


@lru_cache(maxsize=40)
def classification(filename,digest):
    path=ROOT/filename
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('industry classification hash changed')
    with gzip.open(path,'rt') as f:return json.load(f)


def lookup(code,day):
    when=date.fromisoformat(day)
    eligible=[r for r in manifest() if date.fromisoformat(r['available_date'])<when]
    if not eligible:return None
    latest=max(eligible,key=lambda r:r['available_date'])
    row=classification(latest['file'],latest['classification_sha256']).get(code.split('.')[-1])
    if row is None:return None
    return {**row,**{k:latest[k] for k in ('period','available_date','taxonomy','source')},
            'publication_age_days':(when-date.fromisoformat(latest['available_date'])).days}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);a=p.parse_args()
    for row in build(a.root):print(row['period'],row['available_date'],row['row_count'],row['ambiguous_codes'])
