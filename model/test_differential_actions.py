import gzip,json,unittest
from pathlib import Path
from action_verification import apply_verified_actions
from total_return import events_from_snapshot,build,analyze,CoverageError

ROOT=Path(__file__).resolve().parents[1]/'results/action-audit-2026-11-17'

class DifferentialActions(unittest.TestCase):
    def test_four_announced_events_against_real_daily_prices(self):
        for code,day,cash,shares in [('sh.601966','2024-06-14',.377,0),('sh.688320','2024-06-14',.11038,0),
                                     ('sz.002043','2026-06-01',.312,0),('sz.001323','2025-08-21',0,.1),
                                     ('sz.001323','2025-06-09',1,0),('sh.601966','2025-07-10',.084,0)]:
            with self.subTest(code=code):
                with gzip.open(ROOT/(code+'.json.gz'),'rt') as f:d=json.load(f)
                changes=apply_verified_actions(d,'2026-11-17');self.assertTrue(changes)
                before=max(r['date'] for r in d['daily'] if r['date']<day)
                events=events_from_snapshot(d,before,day)
                self.assertEqual(events[day]['cash'],cash);self.assertEqual(events[day]['shares'],shares)
                series=build(d['daily'],events,before,day)
                prices={r['date']:float(r['close']) for r in d['daily']}
                self.assertAlmostEqual(series[-1]['index'],(prices[day]*(1+shares)+cash)/prices[before])
                self.assertEqual(apply_verified_actions(d,'2026-11-17'),[])
                if code!='sh.601966':analyze(d,'2023-10-31','2026-10-30')

    def test_linglong_pipeline_with_saved_supplement(self):
        import tempfile
        from risk_pipeline import reconstruct
        with gzip.open(ROOT/'sh.601966.json.gz','rt') as f:d=json.load(f)
        dates=sorted(r['date'] for r in d['daily']);cal=dict(dates=dates,start=dates[0],end=dates[-1])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sh.601966.json';path.write_text(json.dumps(d));original=path.read_bytes()
            result=reconstruct('601966','2026-11-17',json.loads((ROOT/'601966-dividends.json').read_text()),cal,tmp)
            with gzip.open(ROOT/'601966-risk.json.gz','rt') as f:stored=json.load(f)
            self.assertAlmostEqual(result['vol'],stored['vol'],places=10)
            self.assertEqual(path.read_bytes(),original)

    def test_reference_amount_never_replaces_investor_cash(self):
        rows=[{'date':'2025-01-01','close':10,'preclose':10},{'date':'2025-01-02','close':9.5,'preclose':9.5}]
        series=build(rows,{'2025-01-02':{'cash':1,'shares':0,'reference_cash':.5}},'2025-01-01','2025-01-02')
        self.assertAlmostEqual(series[-1]['index'],1.05)
        with self.assertRaises(CoverageError):build(rows,{'2025-01-02':{'cash':1,'shares':0}},'2025-01-01','2025-01-02')

    def test_unverified_reference_rejected(self):
        event={'dividOperateDate':'2025-01-02','dividCashPsBeforeTax':'1','reference_cash':'.5'}
        with self.assertRaises(CoverageError):events_from_snapshot({'dividend':[event]},'2025-01-01','2025-01-02')

    def test_correction_not_used_before_publication(self):
        with gzip.open(ROOT/'sh.688320.json.gz','rt') as f:d=json.load(f)
        old=json.dumps(d,sort_keys=True)
        self.assertEqual(apply_verified_actions(d,'2024-06-07'),[])
        self.assertEqual(json.dumps(d,sort_keys=True),old)
