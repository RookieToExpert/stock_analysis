#!/usr/bin/env python3
"""Archive public CAPCO industry tables from the official site's static data files."""
import argparse,concurrent.futures,gzip,hashlib,json,re,subprocess,html
from pathlib import Path
import requests


def collect(item,output,cache):
    key=item['period'];dest=output/(key+'.json')
    if dest.exists() and json.loads(dest.read_text()).get('complete'):return json.loads(dest.read_text())
    s=requests.Session();s.trust_env=False;s.headers['User-Agent']='Mozilla/5.0';result={**item,'complete':False,'documents':[]}
    try:
        r=s.get(item['page'],timeout=(8,20));r.raise_for_status();body=r.content
        with gzip.open(output/(key+'-page.js.gz'),'wb') as f:f.write(body)
        result['page_sha256']=hashlib.sha256(body).hexdigest()
        text=body.decode('utf-8');payload=json.loads(text[text.index('{'):].strip().rstrip(';'))
        if payload['date']!=item['available_date']:raise ValueError('publication date mismatch')
        links=re.findall(r'href="([^"]+)"[^>]*>([^<]+)</a>',payload['text'])
        for i,(url,label) in enumerate(links):
            url=html.unescape(url).strip()
            if '.pdf' not in url.lower():continue
            doc_key=key+'-'+str(i);pdf=cache/(doc_key+'.pdf')
            if not pdf.exists():
                r=s.get(url,timeout=(8,25));r.raise_for_status()
                if not r.content.startswith(b'%PDF'):raise ValueError('not a PDF')
                pdf.write_bytes(r.content)
            text=subprocess.run(['pdftotext','-layout',str(pdf),'-'],capture_output=True,check=True,timeout=30).stdout.decode()
            with gzip.open(output/(doc_key+'.txt.gz'),'wt') as f:f.write(text)
            result['documents'].append(dict(key=doc_key,source=url,label=label,pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),text_sha256=hashlib.sha256(text.encode()).hexdigest()))
        if not result['documents']:raise ValueError('no PDF attachment')
        result['complete']=True
    except (requests.RequestException,ValueError,KeyError,OSError,subprocess.SubprocessError) as exc:result['error']=str(exc)
    finally:s.close()
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('cache',type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);a.cache.mkdir(parents=True,exist_ok=True)
    s=requests.Session();s.trust_env=False;s.headers['User-Agent']='Mozilla/5.0'
    r=s.get('https://www.capco.org.cn/',timeout=(8,20));r.raise_for_status()
    asset=re.search(r'src="\./(assets/index-[^"]+\.js)"',r.content.decode())[1];url='https://www.capco.org.cn/'+asset
    r=s.get(url,timeout=(8,20));r.raise_for_status();bundle=r.content.decode('utf-8')
    with gzip.open(a.output/'capco-site-index.js.gz','wb') as f:f.write(r.content)
    queue=[]
    for m in re.finditer(r'title:"((20\d{2})年([上下])半年上市公司行业分类结果)",articleUrl:"([^"]+)",date:"(\d{4}-\d{2}-\d{2})"',bundle):
        queue.append(dict(period=m[2]+'H'+('1' if m[3]=='上' else '2'),available_date=m[5],title=m[1],page='https://www.capco.org.cn/dataFile/'+m[4],index_url=url,taxonomy='CAPCO2023'))
    queue=list({r['period']:r for r in queue}.values());(a.output/'capco-queue.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n');s.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for r in pool.map(lambda x:collect(x,a.output,a.cache),queue):print(r['period'],r['complete'],len(r['documents']),r.get('error',''),flush=True)
