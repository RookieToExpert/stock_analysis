import copy
import gzip
import json
import unittest
from pathlib import Path
from action_verification import apply_verified_actions
from total_return import analyze,CoverageError

ROOT=Path(__file__).parent/'fixtures/verified_actions'


def sample():
    with gzip.open(ROOT/'sh.600007.json.gz','rt') as f:return json.load(f)


class VerifiedActions(unittest.TestCase):
    def test_real_special_dividend_corrected_with_audit(self):
        d=sample()
        with self.assertRaisesRegex(CoverageError,'2024-06-24'):analyze(d,'2023-10-31','2026-10-30')
        changes=apply_verified_actions(d,'2026-11-16')
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]['original']['dividCashPsBeforeTax'],'0.8')
        self.assertEqual(analyze(d,'2023-10-31','2026-10-30')['events']['2024-06-24']['cash'],1.3)
        self.assertEqual(apply_verified_actions(d,'2026-11-16'),[])

    def test_future_evidence_and_other_security_not_applied(self):
        for day,code in [('2024-06-17','sh.600007'),('2026-11-16','sh.600008')]:
            d=sample();d['code']=code;before=copy.deepcopy(d)
            self.assertEqual(apply_verified_actions(d,day),[])
            self.assertEqual(d,before)

    def test_source_changed_not_silently_overridden(self):
        d=sample()
        for row in d['dividend']:
            if row['dividOperateDate']=='2024-06-24':row['dividCashPsBeforeTax']='0.7'
        with self.assertRaisesRegex(CoverageError,'source changed'):apply_verified_actions(d,'2026-11-16')

    def test_pipeline_uses_verified_correction(self):
        import tempfile
        from risk_pipeline import reconstruct
        d=sample();days=sorted(r['date'] for r in d['daily'])
        cal={'start':days[0],'end':days[-1],'dates':days}
        evidence=Path(__file__).resolve().parents[1]/'results/expanded-risk-2026-11-16'
        dividends=json.loads((evidence/'600007-dividends.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'sh.600007.json';p.write_text(json.dumps(d));original=p.read_bytes()
            result=reconstruct('600007','2026-11-16',dividends,cal,temp)
            self.assertEqual(result['source']['events']['2024-06-24']['cash'],1.3)
            self.assertEqual(len(result['source']['verified_actions']),3)
            with gzip.open(evidence/'600007-risk.json.gz','rt') as f:stored=json.load(f)
            self.assertAlmostEqual(result['vol'],stored['vol'],places=10)
            self.assertEqual(p.read_bytes(),original)
