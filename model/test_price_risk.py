import unittest
from price_risk import calculate
from score import evaluate
from test_v033 import fixture


def bars():
    return [f'{m//12:04}-{m%12+1:02}-28,10,10,12,9' for m in range(2023*12+9,2026*12+10)]


class PriceRisk(unittest.TestCase):
    def test_consistent_scale_and_partial_month(self):
        rows=bars()+['2026-11-16,100,100,101,99']
        r=calculate(rows,'2026-11-16')
        self.assertEqual(r['status'],'proxy')
        self.assertAlmostEqual(r['drawdown'],100/6)
        self.assertEqual(r['vol'],0)
        self.assertEqual(len(r['closes']),37)
        self.assertEqual(r['reference_date'],'2026-10-28')

    def test_missing_month_unknown(self):
        for rows in (bars()[:-1], bars()[1:], bars()[:10]+bars()[11:]):
            self.assertEqual(calculate(rows,'2026-11-16')['status'],'unknown')

    def test_bad_prices_not_silently_skipped(self):
        for bad in ('0','-1','nan','inf','13'):
            rows=bars();parts=rows[1].split(',');parts[2]=bad;rows[1]=','.join(parts)
            self.assertIsNone(calculate(rows,'2026-11-16')['vol'])

    def test_duplicate_and_malformed(self):
        for rows in (bars()+[bars()[0]], ['broken']):
            self.assertEqual(calculate(rows,'2026-11-16')['status'],'unknown')

    def test_intraday_quote_never_divided_by_adjusted_high(self):
        d=fixture();d['price_risk']=calculate(bars(),'2026-11-16')
        d['price']=100000
        self.assertAlmostEqual(evaluate(d)['metrics']['drawdown'],100/6)
        self.assertTrue(evaluate(d)['人工警示'])

    def test_unknown_does_not_fallback_to_raw_quote(self):
        d=fixture();d['price_risk']=calculate([],'2026-11-16')
        self.assertIsNone(evaluate(d)['metrics']['drawdown'])


class BalanceCoverage(unittest.TestCase):
    def test_lease_not_current_portion_twice(self):
        from score import balance_metrics
        r=balance_metrics(dict(LEASE_LIAB=20, NONCURRENT_LIAB_1YEAR=10,
                               SHORT_LOAN=30,LONG_LOAN=40,BOND_PAYABLE=50))
        self.assertEqual(r['debt'],150)

    def test_missing_field_is_not_zero(self):
        from score import balance_metrics, SchemaError
        with self.assertRaises(SchemaError): balance_metrics({'SHORT_LOAN':1})
        self.assertIsNone(balance_metrics({})['debt'])

    def test_unlisted_lease_in_existing_statement(self):
        from score import balance_metrics
        self.assertEqual(balance_metrics({'LEASE_LIAB':None})['debt'],0)
