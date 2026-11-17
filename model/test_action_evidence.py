import gzip
import hashlib
import json
from pathlib import Path
import unittest
from extract_action_evidence import extract

ROOT=Path(__file__).resolve().parents[1]


class ActionEvidence(unittest.TestCase):
    def test_archived_issuer_formulas_reproduce_all_mechanical_corrections(self):
        root=ROOT/'results/action-announcements-2026-11-17'
        docs={}
        for p in root.glob('*.json'):
            for doc in json.loads(p.read_text()).get('documents',[]):
                docs[doc['source']]=doc
        count=0
        for fix in json.loads((ROOT/'model/verified_actions.json').read_text()):
            if fix.get('verification_method')!='issuer PDF exact expression; actual entitlement and date matched':continue
            with self.subTest(code=fix['code'],day=fix['ex_date']):
                doc=docs[fix['source']]
                with gzip.open(root/(doc['article']+'.txt.gz'),'rt') as f:text=f.read()
                row=dict(dividCashPsBeforeTax=fix['cash'],dividReserveToStockPs=fix['shares'])
                result=extract(text,doc,fix['code'],fix['ex_date'],row)
                self.assertIsNotNone(result)
                for key in ('cash','shares','reference_cash','reference_shares'):
                    self.assertEqual(result[key],fix[key])
                count+=1
        self.assertEqual(count,240)

    def test_wrong_date_issuer_future_source_and_ambiguous_formula_refused(self):
        text='证券代码：600001 每10股派发现金10元 股权登记日2024年6月4日 除息日为2024年6月5日 (前收盘价-0.9)/(1+0)'
        row=dict(dividCashPsBeforeTax='1')
        def run(text=text,code='sh.600001',day='2024-06-05',available='2024-06-03'):
            doc=dict(available_date=available,text_sha256=hashlib.sha256(text.encode()).hexdigest(),pdf_sha256='archived',source='issuer')
            return extract(text,doc,code,day,row)
        self.assertIsNotNone(run())
        self.assertIsNone(run(day='2024-06-04'))
        self.assertIsNone(run(code='sh.600002'))
        self.assertIsNone(run(available='2024-06-06'))
        self.assertIsNone(run(text=text+' (前收盘价-0.8)/(1+0)'))
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            extract(text,dict(available_date='2024-06-03',text_sha256='changed'),'sh.600001','2024-06-05',row)
