import unittest
from st_release_evidence import extract


class ReleaseEvidence(unittest.TestCase):
    def test_all_archived_machine_proofs_reproduce_and_terminal_notices_fail(self):
        import gzip
        import hashlib
        import json
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        ledger=json.loads((root/'model/verified_st_releases.json').read_text())
        count=0
        for proof in ledger:
            if 'extraction_method' not in proof:continue
            path=root/proof['source_text_path']
            with gzip.open(path,'rt',newline='') as f:text=f.read()
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),proof['source_text_sha256'])
            meta=json.loads(path.with_suffix('').with_suffix('.json').read_text())
            parsed=extract(meta,text)
            self.assertIsNotNone(parsed,proof['code'])
            self.assertTrue(all(proof[k]==v for k,v in parsed.items()))
            count+=1
        self.assertEqual(count,447)
        directory=root/'results/st-source-audit-2026-11-17/pending-reports'
        terminal=0
        for path in directory.glob('*.json'):
            meta=json.loads(path.read_text())
            if not isinstance(meta,dict) or not any(w in meta.get('title','') for w in ('终止上市','退市整理')):continue
            with gzip.open(path.with_suffix('.txt.gz'),'rt') as f:text=f.read()
            self.assertIsNone(extract(meta,text))
            terminal+=1
        self.assertGreater(terminal,50)
        from eligibility_audit import verified_release
        unresolved=json.loads((root/'results/st-source-audit-2026-11-17/unresolved-releases.json').read_text())
        self.assertEqual(len(unresolved),10)
        for row in unresolved:
            self.assertFalse(verified_release(row['code'],row['effective_date']))

    def test_explicit_date_name_and_security_binding(self):
        meta={'code':'sh.600779','statDate':'2016-05-09','available_date':'2016-05-06',
              'title':'关于股票撤销退市风险警示的公告'}
        text='股票代码：600779。撤销退市风险警示的起始日：2016 年5月9日；股票简称由“*ST水井”变更为“水井坊”。'
        self.assertEqual(extract(meta,text)['new_name'],'水井坊')
        for changed in (text.replace('水井坊','ST水井'),text.replace('水井坊','退市水井'),
                        text.replace('600779','600778'),text.replace('5月9日','5月10日'),
                        text.replace('变更为','拟变更为'),text.replace('起始日','申请日')):
            self.assertIsNone(extract(meta,changed))
        for patch in ({'title':'关于申请撤销风险警示的公告'}, {'available_date':'2016-05-09'},
                      {'title':'关于终止上市及撤销风险警示的公告'}):
            self.assertIsNone(extract({**meta,**patch},text))

    def test_unrelated_historical_name_change_does_not_certify_current_date(self):
        meta={'code':'sz.000001','statDate':'2020-05-09','available_date':'2020-05-08',
              'title':'关于撤销风险警示的公告'}
        text='证券代码000001。2018年5月9日起撤销风险警示，股票简称由“ST历史”变更为“历史公司”。'
        text+='其他事项。'*100+'2020年5月9日起撤销退市风险警示，仍实施其他风险警示。'
        self.assertIsNone(extract(meta,text))
