#!/usr/bin/env python3
"""Collect issuer PDFs for an explicit audit queue, via direct HTTP only.

No market-data sessions; writes only the requested output/cache directories.
Collection is evidence acquisition, never automatic approval of a correction.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import requests

INDEX='https://np-anotice-stock.eastmoney.com/api/security/ann'


def collect(item, output, cache):
    code=item['code'];day=re.search(r'\d{4}-\d{2}-\d{2}',item.get('reason',item.get('error','')))[0]
    key=code+'-'+day;dest=output/(key+'.json')
    if dest.exists():
        prior=json.loads(dest.read_text())
        if prior.get('complete'):return prior
    session=requests.Session();session.trust_env=False
    result={'code':code,'target_date':day,'documents':[],'complete':False}
    try:
        params=dict(sr=-1,page_size=100,page_index=1,ann_type='A',client_source='web',
                    stock_list=code[3:],begin_time=str(date.fromisoformat(day)-timedelta(days=45)),end_time=day)
        response=session.get(INDEX,params=params,timeout=(8,20));response.raise_for_status()
        index=response.json();result['index_url']=response.url
        if index.get('success')!=1:raise ValueError('announcement index did not succeed')
        data=index['data']
        if data['total_hits']>100:raise ValueError('announcement page truncated')
        for row in data['list']:
            if code[3:] not in {c['stock_code'] for c in row['codes']}:continue
            title=row['title']
            if not (any(c['column_code']=='001002002001005' for c in row['columns'])
                    or re.search('除权.*参考|重整.*转增|配股.*结果',title)):continue
            article=row['art_code']
            if not re.fullmatch(r'AN\d+',article):raise ValueError('invalid article identifier')
            url='https://pdf.dfcfw.com/pdf/H2_'+article+'_1.pdf'
            pdf=cache/(article+'.pdf')
            if not pdf.exists():
                response=session.get(url,timeout=(8,20));response.raise_for_status()
                if not response.content.startswith(b'%PDF'):raise ValueError('not a PDF')
                pdf.write_bytes(response.content)
            text=subprocess.run(['pdftotext','-layout',str(pdf),'-'],check=True,capture_output=True,timeout=20).stdout.decode()
            with gzip.open(output/(article+'.txt.gz'),'wt') as f:f.write(text)
            result['documents'].append(dict(title=title,available_date=row['notice_date'][:10],source=url,
                article=article,pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                text_sha256=hashlib.sha256(text.encode()).hexdigest()))
        result['complete']=True
    except (requests.RequestException,ValueError,KeyError,OSError,subprocess.SubprocessError) as exc:
        result['error']=str(exc)
    finally:session.close()
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('queue','output','cache'):p.add_argument(name,type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);a.cache.mkdir(parents=True,exist_ok=True)
    queue=json.loads(a.queue.read_text())
    if isinstance(queue,dict):queue=[r for r in queue['rows'] if r['status']=='failed']
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(collect,row,a.output,a.cache) for row in queue]
        for n,future in enumerate(as_completed(futures),1):
            result=future.result()
            print(n,len(queue),result['code'],len(result['documents']),result.get('error','ok'),flush=True)
