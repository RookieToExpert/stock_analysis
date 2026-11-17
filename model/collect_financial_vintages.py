#!/usr/bin/env python3
import requests,json,re,concurrent.futures,pathlib,time
import argparse
out=None
def collect(item):
 code=item['code'];last=int(item['statDate'][:4]);years=set(range(last-4,last+1));path=out/(code+'-index.json')
 if path.exists():return json.loads(path.read_text())
 session=requests.Session();session.trust_env=False;found=[];result=dict(code=code,years=sorted(years),complete=False)
 try:
  for page in range(1,21):
   response=session.get('https://np-anotice-stock.eastmoney.com/api/security/ann',params=dict(sr=-1,page_size=100,page_index=page,ann_type='A',client_source='web',stock_list=code[3:],begin_time=str(last-3)+'-01-01',end_time=str(last+1)+'-12-31'),timeout=(8,20));response.raise_for_status();body=response.json();assert body['success']==1;data=body['data']
   for row in data['list']:
    if code[3:] not in {r['stock_code'] for r in row['codes']}:continue
    if not any(r['column_code']=='001001001001001' or r.get('column_name')=='年度报告全文' for r in row['columns']):continue
    match=re.search(r'(20\d{2})\s*年?年度报告',row['title'])
    if match and int(match[1]) in years:found.append(dict(year=int(match[1]),article=row['art_code'],available_date=row['notice_date'][:10],title=row['title'],source='https://pdf.dfcfw.com/pdf/H2_'+row['art_code']+'_1.pdf'))
   if page*100>=data['total_hits']:result['complete']=True;break
  result.update(documents=found,total_hits=data['total_hits'],pages=page,index_url=response.url)
 except Exception as e:result.update(documents=found,error=str(e))
 finally:session.close()
 path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description='Archive first indexed annual reports and all amendments; direct HTTP only.')
 p.add_argument('reviews',type=pathlib.Path);p.add_argument('output',type=pathlib.Path)
 a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=True)
 reviews=json.loads(a.reviews.read_text())
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  for result in pool.map(collect,reviews):print(result['code'],len(result['documents']),result['complete'],flush=True)
 queue=[]
 for p in out.glob('*-index.json'):
  r=json.loads(p.read_text())
  if not r['complete']:continue
  for year in r['years']:
   matches=sorted((d for d in r['documents'] if d['year']==year),key=lambda d:(d['available_date'],'更正' in d['title'] or '修订' in d['title'],d['article']))
   if matches:queue.append(dict(code=r['code'],statDate=str(year)+'-12-31',source=matches[0]['source'],available_date=matches[0]['available_date'],title=matches[0]['title'],vintage='earliest_indexed_report_not_automatically_certified_original'))
 (out/'queue.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n');print('queue',len(queue))
