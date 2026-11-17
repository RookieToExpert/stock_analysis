#!/usr/bin/env python3
"""Offline replay of saved supplemental dividends; no data-provider session."""
import argparse,gzip,json,hashlib
from collections import Counter
from pathlib import Path
from risk_pipeline import reconstruct
import score


def replay(root, baseline, supplements, output):
    output.mkdir(parents=True,exist_ok=True)
    with gzip.open(baseline,'rt') as f:base=json.load(f)
    manifest=json.loads((supplements/'manifest.json').read_text())
    if hashlib.sha256(baseline.read_bytes()).hexdigest()!=manifest['baseline_sha256']:
        raise ValueError('supplement baseline hash mismatch')
    as_of=manifest['as_of']
    hashes={r['code']:r.get('sha256') for r in base['rows']}
    rows=[]
    for p in sorted(supplements.glob('s[hz].*.json.gz')):
        with gzip.open(p,'rt') as f:old=json.load(f)
        code=old['code'];row={'code':code,'before':old['status']}
        try:
            digest=hashlib.sha256((root/(code+'.json')).read_bytes()).hexdigest()
            if digest!=hashes.get(code):raise ValueError('baseline input changed; comparison invalid')
            risk=reconstruct(code[3:],as_of,old['dividends'],base['calendar'],root)
            row.update(status='reconstructed',metrics={k:risk[k] for k in ('vol','drawdown','total_return')},
                       precision_changes=len(risk['source']['precision_changes']))
            if old['status']!='reconstructed':
                with gzip.open(output/(code+'-risk.json.gz'),'wt') as f:json.dump(risk,f,ensure_ascii=False)
        except (OSError,ValueError,KeyError,TypeError) as e:
            reason=str(e)
            category=('unsupported_paid_rights' if 'unsupported paid_rights' in reason
                      else 'unexplained_reference_price' if 'unexplained reference price' in reason
                      else 'conflicting_action' if 'conflict' in reason
                      else 'missing_action' if 'adjustment without' in reason
                      else 'input_changed' if 'baseline input changed' in reason
                      else 'other')
            row.update(status='failed',reason=reason,category=category)
        rows.append(row)
    result={'revision':score.CALCULATION_REVISION,'as_of':as_of,
            'ledger_sha256':hashlib.sha256(Path(__file__).with_name('verified_actions.json').read_bytes()).hexdigest(),
            'unsupported_ledger_sha256':hashlib.sha256(Path(__file__).with_name('unsupported_actions.json').read_bytes()).hexdigest(),
            'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
            'counts':dict(Counter(r['status'] for r in rows)),
            'failure_categories':dict(Counter(r['category'] for r in rows if r['status']=='failed')),
            'recovered':[r['code'] for r in rows if r['before']=='failed' and r['status']=='reconstructed'],
            'regressions':[r['code'] for r in rows if r['before']=='reconstructed' and r['status']!='reconstructed'],
            'rows':rows,'issuer_certified':False}
    (output/'replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','baseline','supplements','output'):p.add_argument(key,type=Path)
    a=p.parse_args();r=replay(a.root,a.baseline,a.supplements,a.output)
    print(json.dumps({k:v for k,v in r.items() if k!='rows'},ensure_ascii=False))
