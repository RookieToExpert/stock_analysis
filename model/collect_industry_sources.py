#!/usr/bin/env python3
"""Archive dated CSRC industry publications; direct HTTP, no stock download session."""
import argparse,concurrent.futures,gzip,hashlib,json,re,subprocess
from pathlib import Path
from urllib.parse import urljoin
import requests


def collect(item,output,cache):
    dest=output/(item['period']+'.json')
    if dest.exists():
        old=json.loads(dest.read_text())
        if old.get('complete'):return old
    session=requests.Session();session.trust_env=False;session.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://www.csrc.gov.cn/csrc/c100103/common_list.shtml'});result=dict(item,complete=False,documents=[])
    try:
        response=session.get(item['page'],timeout=(8,20));response.raise_for_status();body=response.content
        html=body.decode('utf-8');result['page_sha256']=hashlib.sha256(body).hexdigest()
        with gzip.open(output/(item['period']+'-page.html.gz'),'wb') as f:f.write(body)
        links=list(dict.fromkeys(urljoin(item['page'],u) for u in re.findall(r'href=["\']([^"\']+\.pdf)["\']',html,re.I)))
        if not links:raise ValueError('no PDF attachment')
        for i,url in enumerate(links):
            key=item['period']+'-'+str(i);pdf=cache/(key+'.pdf')
            if not pdf.exists():
                r=session.get(url,timeout=(8,20));r.raise_for_status()
                if not r.content.startswith(b'%PDF'):raise ValueError('not a PDF')
                pdf.write_bytes(r.content)
            text=subprocess.run(['pdftotext','-layout',str(pdf),'-'],capture_output=True,check=True,timeout=30).stdout.decode()
            with gzip.open(output/(key+'.txt.gz'),'wt') as f:f.write(text)
            result['documents'].append(dict(source=url,key=key,pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),text_sha256=hashlib.sha256(text.encode()).hexdigest()))
        result['complete']=True
    except (requests.RequestException,ValueError,OSError,subprocess.SubprocessError) as exc:result['error']=str(exc)
    finally:session.close()
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('cache',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);a.cache.mkdir(parents=True,exist_ok=True)
    queue=[];session=requests.Session();session.trust_env=False;session.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://www.csrc.gov.cn/csrc/c100103/common_list.shtml'})
    for suffix in ('','_2'):
        url='https://www.csrc.gov.cn/csrc/c100103/common_list'+suffix+'.shtml'
        r=session.get(url,timeout=(8,20));r.raise_for_status()
        with gzip.open(a.output/('index'+suffix+'.html.gz'),'wb') as f:f.write(r.content)
        for item in re.findall(r'<li>(.*?)</li>',r.content.decode('utf-8'),re.S):
            match=re.search(r'href="([^"]+)"[^>]*>(20\d{2})年([1-4])季度上市公司行业分类结果',item)
            published=re.search(r'<span class="date">(\d{4}-\d{2}-\d{2})</span>',item)
            if match and published and (int(match[2]),int(match[3]))>=(2016,4):
                queue.append(dict(period=match[2]+'Q'+match[3],available_date=published[1],page=urljoin(url,match[1]),index_url=url,taxonomy='CSRC2012'))
    session.close();(a.output/'queue.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for r in pool.map(lambda x:collect(x,a.output,a.cache),queue):print(r['period'],r['complete'],len(r['documents']),r.get('error',''),flush=True)
