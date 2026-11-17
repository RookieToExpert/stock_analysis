#!/usr/bin/env python3
"""串行直连补查固定失败清单，只读下载目录；每只最多请求一次并逐只保存证据。"""
import argparse,gzip,hashlib,json,time
from pathlib import Path
import score
from risk_pipeline import reconstruct


def run(root, baseline, output, as_of):
    output.mkdir(parents=True,exist_ok=True)
    manifest=output/'manifest.json'
    expected={'as_of':as_of,'baseline':str(baseline.resolve()),
              'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
              'calculation_revision':score.CALCULATION_REVISION}
    if manifest.exists() and json.loads(manifest.read_text())!=expected:
        raise ValueError('audit output belongs to another run')
    manifest.write_text(json.dumps(expected,indent=2))
    with gzip.open(baseline,'rt') as f:base=json.load(f)
    targets=[r for r in base['rows'] if r.get('status')=='failed' and r.get('reason')!='incomplete calendar']
    for n,row in enumerate(targets,1):
        code=row['code'];target=output/(code+'.json.gz')
        if target.exists():continue
        result={'code':code,'previous_error':row['reason']}
        try:
            original_get=score.get
            try:
                score.get=lambda url,attempts=1:original_get(url,attempts=1)
                dividends=score.dividend_rows(code[3:])
            finally:
                score.get=original_get
            result['dividends']=dividends
            result['risk']=reconstruct(code[3:],as_of,dividends,base['calendar'],root)
            result['status']='reconstructed'
        except (OSError,ValueError,TypeError,KeyError) as exc:
            result.update(status='failed',error=type(exc).__name__+': '+str(exc))
        tmp=target.with_suffix('.tmp')
        with gzip.open(tmp,'wt') as f:json.dump(result,f,ensure_ascii=False)
        tmp.replace(target)
        if n%20==0:print(n,'/',len(targets),flush=True)
        time.sleep(.3)
    print('complete',len(targets),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);p.add_argument('--as-of',required=True)
    a=p.parse_args();run(a.root,a.baseline,a.output,a.as_of)
