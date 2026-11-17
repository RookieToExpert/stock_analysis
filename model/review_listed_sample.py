"""Reproduce listing-valid report selection from frozen minimal provider inputs."""
import argparse
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import re
from issuer_sampling import latest_listed_annual


def review(inputs, reports, as_of, fallback_reports=None):
    results=[]
    for item in inputs:
        row=latest_listed_annual(item['data'],as_of,item['period_ceiling'])
        result={'code':item['data']['code'],'original_period':item['period_ceiling'],
                'selected':row,'status':'no_listing_valid_report'}
        if row:
            key=item['data']['code']+'-'+row['statDate']
            source_dir=reports
            if not (source_dir/(key+'.json')).exists() and fallback_reports is not None:
                source_dir=fallback_reports
            meta_path=source_dir/(key+'.json')
            result['status']='issuer_source_not_archived'
            if meta_path.exists():
                meta=json.loads(meta_path.read_text())
                with gzip.open(source_dir/(key+'.txt.gz'),'rt',newline='') as f:text=f.read()
                if hashlib.sha256(text.encode()).hexdigest()!=meta['text_sha256']:
                    raise ValueError('source hash mismatch: '+key)
                token=f"{Decimal(row['netProfit']):,.2f}"
                normalized=re.sub(r'\s+',' ',text)
                position=normalized.find(token)
                result.update(source=meta['source'],source_text_sha256=meta['text_sha256'],
                    numeric_literal_found=position>=0,
                    publication_date_matches=row['pubDate']==meta.get('available_date',meta.get('supplier_pubDate')),
                    excerpt=normalized[max(0,position-100):position+len(token)+100] if position>=0 else '',
                    status='numeric_and_date_check_only_not_full_vintage_certification')
        results.append(result)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inputs','reports','output'):p.add_argument(name,type=Path)
    p.add_argument('--fallback-reports',type=Path)
    p.add_argument('--as-of',required=True);a=p.parse_args()
    a.output.write_text(json.dumps(review(json.loads(a.inputs.read_text()),a.reports,a.as_of,a.fallback_reports),ensure_ascii=False,indent=2)+'\n')
