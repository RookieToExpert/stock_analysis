import copy
from datetime import date
import gzip
import json
from pathlib import Path
import unittest

from backtest import Portfolio, Lot
from rights import apply_verified_rights
from total_return import analyze, events_from_snapshot, build, CoverageError
from action_verification import exclude_verified_adjustments

ROOT=Path(__file__).resolve().parents[1]
EVENT=json.loads((ROOT/'model/verified_rights.json').read_text())[0]


class PaidRights(unittest.TestCase):
    def snapshot(self,code='sz.000049'):
        with gzip.open(ROOT/'results/action-announcements-2026-11-17'/f'{code}-input.json.gz','rt') as f:
            return json.load(f)

    def test_subscription_capital_is_not_return_or_free_shares(self):
        d=self.snapshot()
        apply_verified_rights(d,'2026-11-17','2023-10-31','2026-10-30')
        events=events_from_snapshot(d,'2023-11-29','2023-12-08')
        result=build(d['daily'],events,'2023-11-29','2023-12-08')
        self.assertAlmostEqual(result[-1]['index'],27.35*1.3/(31.54+0.3*21.16))
        self.assertEqual(events['2023-12-08']['rights_shares'],.3)
        self.assertEqual(events['2023-12-08']['reference_rights_shares'],.2847542)
        self.assertNotAlmostEqual(result[-1]['index'],27.35*1.3/31.54)

    def test_future_evidence_and_active_subscription_trading_refused(self):
        d=self.snapshot()
        self.assertEqual(apply_verified_rights(d,'2023-12-07','2023-10-31','2023-12-08'),[])
        with self.assertRaises(CoverageError):events_from_snapshot(d,'2023-11-29','2023-12-08')
        for row in d['daily']:
            if row['date']=='2023-12-01':row['tradestatus']='1'
        with self.assertRaisesRegex(CoverageError,'daily cash-flow model'):
            apply_verified_rights(d,'2026-11-17','2023-10-31','2026-10-30')

    def test_payment_and_listing_preserve_assets_without_early_tradability(self):
        p=Portfolio(10000,lots={'000049':[Lot(1000,date(2023,11,1))]})
        p.record_rights(date(2023,11,29),'000049',EVENT)
        self.assertEqual(p.subscribe_rights(date(2023,11,30),EVENT['id']),300)
        self.assertAlmostEqual(p.cash,3652)
        self.assertEqual(p.shares('000049'),1000)
        self.assertAlmostEqual(p.value({'000049':31.54},date(2023,12,1)),41540)
        self.assertAlmostEqual(p.value({'000049':27.35},date(2023,12,8)),39207)
        with self.assertRaises(ValueError):p.value({'000049':27.35})
        with self.assertRaises(ValueError):p.settle_rights(date(2023,12,22),EVENT['id'])
        p.settle_rights(date(2023,12,25),EVENT['id'])
        self.assertEqual(p.shares('000049'),1300)
        self.assertAlmostEqual(p.value({'000049':27.35}),39207)
        with self.assertRaises(ValueError):p.settle_rights(date(2023,12,25),EVENT['id'])

    def test_partial_subscription_requires_existing_cash_and_entitlement(self):
        p=Portfolio(1000,lots={'000049':[Lot(1000,date(2023,11,1))]})
        p.record_rights(date(2023,11,29),'000049',EVENT)
        with self.assertRaises(ValueError):p.record_rights(date(2023,11,29),'000049',EVENT)
        with self.assertRaises(ValueError):p.subscribe_rights(date(2023,11,29),EVENT['id'])
        with self.assertRaises(ValueError):p.subscribe_rights(date(2023,11,30),EVENT['id'],300)
        self.assertEqual(p.subscribe_rights(date(2023,11,30),EVENT['id']),47)
        self.assertAlmostEqual(p.cash,5.48)
        with self.assertRaises(ValueError):p.subscribe_rights(date(2023,12,7),EVENT['id'])

    def test_verified_bad_factor_is_dated_and_exactly_matched(self):
        d=self.snapshot('sz.000002');original=copy.deepcopy(d)
        self.assertEqual(exclude_verified_adjustments(d,'2026-03-31'),[])
        self.assertEqual(len(exclude_verified_adjustments(d,'2026-04-01')),1)
        analyze(d,'2023-10-31','2026-10-30')
        original['adjust'][-1]['backAdjustFactor']='134.284606'
        with self.assertRaisesRegex(CoverageError,'source changed'):
            exclude_verified_adjustments(original,'2026-04-01')

    def test_new_price_gap_or_action_blocks_factor_exclusion(self):
        for changed in ('price','action'):
            d=self.snapshot('sz.000002')
            if changed=='price':
                next(r for r in d['daily'] if r['date']=='2025-01-09')['preclose']='6.95'
            else:d['dividend'].append(dict(dividOperateDate='2025-01-09',dividCashPsBeforeTax='0.1'))
            with self.assertRaises(CoverageError):exclude_verified_adjustments(d,'2026-04-01')

    def test_fractional_entitlement_and_invalid_evidence_are_not_guessed(self):
        from rights import validate
        p=Portfolio(10000,lots={'000049':[Lot(1001,date(2023,11,1))]})
        with self.assertRaisesRegex(ValueError,'fractional rights'):
            p.record_rights(date(2023,11,29),'000049',EVENT)
        for patch in ({'subscription_price':'invalid'}, {'subscription_price':'NaN'},
                      {'listing_available_date':'2023-12-26'}, {'available_date':'2023-12-09'}):
            event={**EVENT,**patch}
            with self.assertRaises(ValueError):validate(event)
