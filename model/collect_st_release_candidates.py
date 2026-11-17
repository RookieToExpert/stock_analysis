"""Collect dated issuer announcement candidates, without certifying ST removal."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
from pathlib import Path
import requests


def collect(row, output):
    path=output/(row['code']+'-'+row['effective_date']+'.json')
    if path.exists():
        cached=json.loads(path.read_text())
        if cached.get('complete'):return cached
    result={**row,'complete':False,'documents':[]}
    day=date.fromisoformat(row['effective_date'])
    with requests.Session() as session:
        session.trust_env=False
        try:
            for page in range(1,6):
                response=session.get('https://np-anotice-stock.eastmoney.com/api/security/ann',params={
                    'sr':-1,'page_size':100,'page_index':page,'ann_type':'A','client_source':'web',
                    'stock_list':row['code'][3:],'begin_time':str(day-timedelta(days=30)),
                    'end_time':str(day)},timeout=(8,20))
                response.raise_for_status();body=response.json()
                if body.get('success')!=1:raise ValueError('announcement index failed')
                data=body['data']
                for doc in data['list']:
                    if row['code'][3:] not in {c['stock_code'] for c in doc['codes']}:continue
                    if not any(word in doc['title'] for word in ('撤销','撤消','恢复上市','终止上市','退市整理')):continue
                    result['documents'].append(doc)
                result['index_url']=response.url
                if page*100>=data['total_hits']:
                    result['complete']=True;break
        except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
            result['error']=str(exc)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('pending',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);queue=[];statuses=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(lambda row:collect(row,a.output),json.loads(a.pending.read_text())):
            statuses.append({'code':result['code'],'effective_date':result['effective_date'],
                             'complete':result['complete'],'candidates':len(result['documents'])})
            print(statuses[-1],flush=True)
            if not result['complete']:continue
            for doc in result['documents']:
                if any(w in doc['title'] for w in ('申请','核查','意见')):continue
                queue.append({'code':result['code'],'statDate':result['effective_date'],
                    'suffix':'-'+doc['art_code'],'title':doc['title'],
                    'available_date':doc['notice_date'][:10],
                    'source':'https://pdf.dfcfw.com/pdf/H2_'+doc['art_code']+'_1.pdf'})
    (a.output/'queue.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n')
    (a.output/'status.json').write_text(json.dumps(statuses,ensure_ascii=False,indent=2)+'\n')
