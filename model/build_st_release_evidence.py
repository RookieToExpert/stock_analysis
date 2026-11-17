"""Build hash-bound release proofs only for supported explicit announcement passages."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from st_release_evidence import extract

ROOT=Path(__file__).resolve().parents[1]


def build(reports):
    reports=reports.resolve()
    candidates={};review=[]
    for path in sorted(reports.glob('*.json')):
        meta=json.loads(path.read_text())
        if not isinstance(meta,dict) or 'text_sha256' not in meta:continue
        with gzip.open(path.with_suffix('.txt.gz'),'rt',newline='') as f:text=f.read()
        if hashlib.sha256(text.encode()).hexdigest()!=meta['text_sha256']:
            raise ValueError('source hash mismatch: '+str(path))
        proof=extract(meta,text)
        review.append({'file':str(path.relative_to(ROOT)),'matched':proof is not None})
        if not proof:continue
        proof.update(code=meta['code'],source=meta['source'],
                     source_text_path=str(path.with_suffix('.txt.gz').relative_to(ROOT)),
                     source_text_sha256=meta['text_sha256'])
        candidates.setdefault((meta['code'],proof['effective_date']),[]).append(proof)
    proofs=[];conflicts=[]
    for key,rows in sorted(candidates.items()):
        if len({r['new_name'] for r in rows})>1:
            conflicts.append({'code':key[0],'effective_date':key[1],'candidates':rows})
        else:proofs.append(min(rows,key=lambda r:(r['available_date'],r['source'])))
    return {'proofs':proofs,'conflicts':conflicts,'review':review}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('reports',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=build(a.reports)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('proofs',len(result['proofs']),'conflicts',len(result['conflicts']),'reviewed',len(result['review']))
