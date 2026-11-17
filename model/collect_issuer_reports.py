#!/usr/bin/env python3
"""Archive explicit issuer-report sources using direct HTTP, with content hashes.

Evidence collection only: never promotes a report or a blank table cell to verified data.
"""
import requests,json,gzip,subprocess,hashlib,re,html
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from html.parser import HTMLParser
import argparse
root=cache=None
class Text(HTMLParser):
 def __init__(self):super().__init__();self.out=[];self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style'):self.skip+=1
  if tag in ('td','tr','p','div','br'):self.out.append('\n')
 def handle_endtag(self,tag):
  if tag in ('script','style'):self.skip=max(0,self.skip-1)
 def handle_data(self,text):
  if not self.skip:self.out.append(text)
def fetch(row):
 key=row['code']+'-'+row['statDate']+row.get('suffix','');dest=root/(key+'.json')
 if dest.exists():return key,'cached'
 s=requests.Session();s.trust_env=False
 try:
  r=s.get(row['source'],timeout=(8,30));r.raise_for_status();body=r.content
  if body.startswith(b'%PDF'):
   p=cache/(key+'.pdf');p.write_bytes(body);text=subprocess.run(['pdftotext','-layout',str(p),'-'],capture_output=True,check=True,timeout=25).stdout.decode()
  else:
   enc='gb18030' if b'gb2312' in body[:10000].lower() or b'gbk' in body[:10000].lower() else 'utf-8'
   raw=body.decode(enc,errors='replace');parser=Text();parser.feed(raw);text=''.join(parser.out)
  with gzip.open(root/(key+'.txt.gz'),'wt') as f:f.write(text)
  out={**row,'source_sha256':hashlib.sha256(body).hexdigest(),'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'text_length':len(text)};dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');return key,len(text)
 except Exception as e:return key,type(e).__name__+': '+str(e)
 finally:s.close()
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for k in ('queue','output','cache'):p.add_argument(k,type=Path)
 a=p.parse_args();root=a.output;cache=a.cache
 root.mkdir(parents=True,exist_ok=True);cache.mkdir(parents=True,exist_ok=True)
 with ThreadPoolExecutor(max_workers=3) as pool:
  for f in as_completed([pool.submit(fetch,r) for r in json.loads(a.queue.read_text())]):print(f.result(),flush=True)
