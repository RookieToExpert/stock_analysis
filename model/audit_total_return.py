#!/usr/bin/env python3
"""离线复现三只样本与公告补丁。只写指定输出，不修改原始下载文件。"""
import gzip,json
from pathlib import Path
from total_return import analyze,CoverageError


def audit(root):
    overlays=json.loads((root/'action_overlays.json').read_text())
    result={}
    for path in sorted(root.glob('*.json.gz')):
        d=json.loads(gzip.decompress(path.read_bytes()));code=d['code'];entry={}
        try:entry['original']=analyze(d,'2023-10-31','2026-10-30')['metrics']
        except CoverageError as exc:entry['original_error']=str(exc)
        applied=[]
        for event in overlays:
            if event['code']==code:
                if event['announcement_date']>event['dividOperateDate']:
                    raise ValueError('announcement after ex date')
                d['dividend'].append(event);applied.append(event)
        calculation=analyze(d,'2023-10-31','2026-10-30')
        entry.update(after_overlay=calculation['metrics'],overlays=applied,
                     validation=calculation['validation'],assumption=calculation['assumption'])
        result[code]=entry
    return result


if __name__=='__main__':
    print(json.dumps(audit(Path(__file__).parent/'fixtures/total_return'),ensure_ascii=False,indent=2))
