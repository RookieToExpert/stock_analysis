import unittest
from total_return import build,events_from_snapshot,CoverageError


def bar(day,close,preclose):
    return dict(date=day,close=str(close),preclose=str(preclose))


class TotalReturn(unittest.TestCase):
    def test_cash_reinvestment(self):
        s=build([bar('2025-01-01',10,10),bar('2025-01-02',9,9),bar('2025-01-03',9.9,9)],
                {'2025-01-02':dict(cash=1,shares=0)},'2025-01-01','2025-01-03')
        self.assertAlmostEqual(s[1]['index'],1)
        self.assertAlmostEqual(s[2]['index'],1.1)

    def test_bonus_shares(self):
        s=build([bar('2025-01-01',10,10),bar('2025-01-02',5,5)],
                {'2025-01-02':dict(cash=0,shares=1)},'2025-01-01','2025-01-02')
        self.assertEqual(s[-1]['index'],1)

    def test_missing_action_rejected(self):
        with self.assertRaises(CoverageError):
            build([bar('2025-01-01',10,10),bar('2025-01-02',9,9)],{},'2025-01-01','2025-01-02')

    def test_factor_event_without_dividend(self):
        with self.assertRaises(CoverageError):
            events_from_snapshot({'adjust':[{'dividOperateDate':'2025-01-02'}]},'2025-01-01','2025-02-01')

    def test_repeated_cumulative_factors_after_known_event(self):
        event=dict(dividOperateDate='2025-01-02',dividCashPsBeforeTax='0.1')
        factors=[dict(dividOperateDate=day,foreAdjustFactor='0.9',backAdjustFactor='2.1')
                 for day in ('2025-01-02','2025-01-03')]
        snapshot={'dividend':[event],'adjust':factors}
        self.assertEqual(len(events_from_snapshot(snapshot,'2025-01-01','2025-02-01')),1)
        for field,value in [('foreAdjustFactor','0.91'),('backAdjustFactor','2.11'),('backAdjustFactor',None)]:
            bad={'dividend':[event],'adjust':[factors[0],dict(factors[1],**{field:value})]}
            with self.assertRaises(CoverageError):events_from_snapshot(bad,'2025-01-01','2025-02-01')
        with self.assertRaises(CoverageError):
            events_from_snapshot({'adjust':factors},'2025-01-01','2025-02-01')

    def test_repeated_factor_does_not_hide_price_jump(self):
        event=dict(dividOperateDate='2025-01-02',dividCashPsBeforeTax='0.1')
        snapshot={'dividend':[event], 'adjust':[
            dict(dividOperateDate=day,foreAdjustFactor='0.9',backAdjustFactor='2.1')
            for day in ('2025-01-02','2025-01-03')]}
        events=events_from_snapshot(snapshot,'2025-01-01','2025-01-03')
        with self.assertRaises(CoverageError):
            build([bar('2025-01-01',10,10),bar('2025-01-02',9.9,9.9),bar('2025-01-03',9.8,9.8)],
                  events,'2025-01-01','2025-01-03')

    def test_duplicate_action_not_double_counted(self):
        e=dict(dividOperateDate='2025-01-02',dividCashStock='10派1',dividCashPsBeforeTax='0.1')
        self.assertEqual(events_from_snapshot({'dividend':[e,e]},'2025-01-01','2025-02-01')['2025-01-02']['cash'],.1)

    def test_missing_declared_cash_not_zero(self):
        with self.assertRaises(CoverageError):
            events_from_snapshot({'dividend':[dict(dividOperateDate='2025-01-02',dividCashStock='10派1')]},'2025-01-01','2025-02-01')

    def test_nonfinite_rejected(self):
        with self.assertRaises(CoverageError):
            build([bar('2025-01-01',10,10),bar('2025-01-02','nan',10)],{},'2025-01-01','2025-01-02')


class RealSamples(unittest.TestCase):
    def test_real_redundant_factor_is_recorded(self):
        import gzip,json
        from pathlib import Path
        from total_return import analyze
        path=Path(__file__).parent/'fixtures/total_return/sh.600012.json.gz'
        with gzip.open(path,'rt') as f:d=json.load(f)
        result=analyze(d,'2023-10-31','2026-10-30')
        self.assertIn('2024-07-15',result['redundant_adjustment_dates'])
        self.assertNotIn('2024-07-15',result['events'])

    def test_announced_overlays_repair_missing_events(self):
        from pathlib import Path
        from audit_total_return import audit
        result=audit(Path(__file__).parent/'fixtures/total_return')
        self.assertIn('original_error',result['sh.601919'])
        self.assertIn('original_error',result['sh.601225'])
        self.assertNotIn('original_error',result['sh.600900'])
        for row in result.values():
            self.assertGreaterEqual(row['after_overlay']['max_drawdown'],row['after_overlay']['current_drawdown'])
