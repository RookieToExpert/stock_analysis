import copy
import unittest
from rules import dividend_years, missing_fields, metrics, recent_details, recent_state, blue_chip
from score import evaluate
from test_rules import base, yr, row


def fixture(day='2026-05-06'):
    d = base()
    d.update(model_version='0.3.3', as_of=day)
    d['years'].append(copy.deepcopy(d['years'][-1]))
    d['years'][-1]['year'] = '2020'
    d['years'][0].update(paid=None, paid_status='待实施')
    return d


class DividendWindow(unittest.TestCase):
    def test_may_pending_does_not_exclude(self):
        d = fixture()
        self.assertEqual(missing_fields(d), [])
        self.assertEqual(metrics(d)['paid_years'], 5)
        self.assertTrue(blue_chip(d['mv'], metrics(d)))
        self.assertEqual(evaluate(d)['等级'], '合格')

    def test_cutoff_is_fixed_not_status_driven(self):
        d = fixture('2026-06-30')
        self.assertEqual(dividend_years(d)[0]['year'], '2024')
        d['as_of'] = '2026-07-01'
        self.assertEqual(dividend_years(d)[0]['year'], '2025')
        self.assertIn('分红窗口paid缺1年', missing_fields(d))

    def test_missing_old_year_not_skipped(self):
        d = fixture()
        d['years'][-1]['paid'] = None
        self.assertIn('分红窗口paid缺1年', missing_fields(d))

    def test_zero_not_skipped(self):
        d = fixture()
        d['years'][-1]['paid'] = 0
        self.assertEqual(missing_fields(d), [])
        self.assertEqual(metrics(d)['paid_years'], 4)
        self.assertFalse(blue_chip(d['mv'], metrics(d)))

    def test_denominators_align(self):
        d = fixture()
        d['years'][0]['np'] = 1
        self.assertEqual(metrics(d)['payout'], 50)
        d['years'][-1]['invest'] = None
        self.assertIsNone(metrics(d)['invest_vs_paid'])
        self.assertIn('分红窗口invest缺1年', missing_fields(d))


class Recent(unittest.TestCase):
    def test_cumulative_masks_quarter(self):
        rs = [row('2026-09-30',180),row('2026-06-30',160),row('2025-09-30',150),row('2025-06-30',100)]
        detail = recent_details(rs)
        self.assertEqual(detail['quarter_kf_yoy'], -60)
        d = base(); d.update(detail)
        self.assertIn('单季扣非同比-60%', recent_state(metrics(d)))

    def test_loss_expands(self):
        detail = recent_details([row('2026-03-31',-30),row('2025-03-31',-10)])
        self.assertIsNone(detail['quarter_kf_yoy'])
        self.assertIn('单季扣非亏损扩大', detail['profit_deterioration'])

    def test_loss_improves(self):
        detail = recent_details([row('2026-03-31',-5),row('2025-03-31',-10)])
        self.assertEqual(detail['profit_deterioration'], [])
        self.assertTrue(detail['quarter_known'])

    def test_missing_previous_quarter(self):
        detail = recent_details([row('2026-09-30',100),row('2025-09-30',80)])
        self.assertFalse(detail['quarter_known'])

    def test_q4_and_unsorted(self):
        detail = recent_details([row('2025-09-30',80),row('2026-12-31',110),row('2025-12-31',100),row('2026-09-30',100)])
        self.assertEqual(detail['quarter_kf_yoy'], -50)

    def test_legacy_snapshot_dispatch(self):
        import score_v032
        d = base()
        self.assertEqual(evaluate(d), score_v032.evaluate(d))

    def test_unknown_version_rejected(self):
        d = fixture(); d['model_version'] = 'future'
        with self.assertRaises(ValueError): evaluate(d)
