import copy,gzip,json,unittest
from pathlib import Path
from action_verification import apply_verified_actions,check_supported_actions
from action_precision import reconcile_precision
from total_return import events_from_snapshot,build,analyze,CoverageError

ROOT=Path(__file__).resolve().parents[1]/'results/restructuring-audit-2026-11-17'


class RestructuringActions(unittest.TestCase):
    def test_all_new_issuer_fixtures_pass_entire_window(self):
        for path in sorted(ROOT.glob('s[hz].*.json.gz')):
            if path.name.endswith('-risk.json.gz'):continue
            with self.subTest(code=path.name):
                with gzip.open(path,'rt') as f:data=json.load(f)
                apply_verified_actions(data,'2026-11-17')
                reconcile_precision(data)
                result=analyze(data,'2023-10-31','2026-10-30')
                self.assertEqual(result['series'][-1]['date'],'2026-10-30')
                self.assertGreater(result['series'][-1]['index'],0)

    def test_unknown_paid_rights_rejected_only_in_applicable_window(self):
        ledger=[dict(code='sz.000050',ex_date='2023-12-08',available_date='2023-12-08',
                     kind='paid_rights',reason='unverified',source='issuer')]
        with self.assertRaisesRegex(CoverageError,'unsupported paid_rights'):
            check_supported_actions('sz.000050','2023-10-31','2026-10-30','2026-11-17',ledger)
        check_supported_actions('sz.000050','2023-12-08','2026-10-30','2026-11-17',ledger)
        check_supported_actions('sz.000050','2023-10-31','2023-12-07','2023-12-07',ledger)
        check_supported_actions('sz.000050','2023-10-31','2026-10-30','2023-12-07',ledger)
        check_supported_actions('sz.000051','2023-10-31','2026-10-30','2026-11-17',ledger)

    def test_real_restructuring_never_credits_creditor_shares_to_holder(self):
        for code,day in [('600165','2025-12-11'),('600375','2024-12-26'),('600589','2023-12-29'),('600715','2024-12-16')]:
            with self.subTest(code=code):
                with gzip.open(ROOT/('sh.'+code+'.json.gz'),'rt') as f:d=json.load(f)
                before=max(r['date'] for r in d['daily'] if r['date']<day)
                with self.assertRaises(CoverageError):
                    build(d['daily'],events_from_snapshot(d,before,day),before,day)
                apply_verified_actions(d,'2026-11-17')
                events=events_from_snapshot(d,before,day)
                self.assertEqual(events[day]['shares'],0)
                prices={r['date']:float(r['close']) for r in d['daily']}
                result=build(d['daily'],events,before,day)
                self.assertAlmostEqual(result[-1]['index'],prices[day]/prices[before])
                corrupted=copy.deepcopy(d['daily'])
                for r in corrupted:
                    if r['date']==before:r['close']=str(prices[before]+.01)
                with self.assertRaisesRegex(CoverageError,'previous close mismatch'):
                    build(corrupted,events,before,day)

    def test_reference_price_requires_source_and_both_fields(self):
        row=dict(dividOperateDate='2025-01-02',dividCashPsBeforeTax='0',announced_reference_price='8')
        with self.assertRaises(CoverageError):events_from_snapshot({'dividend':[row]},'2025-01-01','2025-01-02')
        row['verified_action_source']='issuer'
        events=events_from_snapshot({'dividend':[row]},'2025-01-01','2025-01-02')
        daily=[dict(date='2025-01-01',close='10'),dict(date='2025-01-02',close='9',preclose='8')]
        with self.assertRaisesRegex(CoverageError,'incomplete announced reference'):
            build(daily,events,'2025-01-01','2025-01-02')

    def test_rounding_only_never_merges_distinct_distributions(self):
        low=dict(dividOperateDate='2025-01-02',dividCashPsBeforeTax='0.199930',dividStocksPs='0',dividReserveToStockPs='')
        high=dict(low,source='eastmoney-RPT_F10_DIVIDEND_MAIN',dividCashPsBeforeTax='0.1999297')
        d={'dividend':[low,high]};self.assertEqual(len(reconcile_precision(d)),1)
        e=events_from_snapshot(d,'2025-01-01','2025-01-02');self.assertEqual(e['2025-01-02']['cash'],.1999297)
        self.assertEqual(reconcile_precision(d),[])
        low['dividCashPsBeforeTax']='0.199931'
        self.assertEqual(reconcile_precision(d),[])
        with self.assertRaises(CoverageError):events_from_snapshot(d,'2025-01-01','2025-01-02')

    def test_boundary_dividend_anchors_duplicate_factor_without_double_payment(self):
        d=dict(dividend=[dict(dividOperateDate='2025-01-01',dividCashPsBeforeTax='1')],
               adjust=[dict(dividOperateDate=day,foreAdjustFactor='1',backAdjustFactor='2') for day in ['2025-01-01','2025-01-02']])
        self.assertEqual(events_from_snapshot(d,'2025-01-01','2025-01-02'),{})
        daily=[dict(date='2025-01-01',close='10'),dict(date='2025-01-02',close='10',preclose='10')]
        self.assertEqual(build(daily,{},'2025-01-01','2025-01-02')[-1]['index'],1)
        d['adjust'][1]['backAdjustFactor']='2.01'
        with self.assertRaises(CoverageError):events_from_snapshot(d,'2025-01-01','2025-01-02')
