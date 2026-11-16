import unittest
from benchmark_data import normalize


def data():return {'url':'official','response':{'code':'200','data':[{'indexCode':'H00300','tradeDate':'20260105','close':100},{'indexCode':'H00300','tradeDate':'20260106','close':101}]}}


class Benchmark(unittest.TestCase):
    def test_normalize(self):
        r=normalize(data(),'H00300',['2026-01-05','2026-01-06'])
        self.assertEqual(r['rows'][-1]['index'],1.01)
    def test_missing_day_rejected(self):
        with self.assertRaises(ValueError):normalize(data(),'H00300',['2026-01-07'])
    def test_price_index_rejected(self):
        with self.assertRaises(ValueError):normalize(data(),'000300',['2026-01-05'])
    def test_extra_day_is_not_invented_session(self):
        r=normalize(data(),'H00300',['2026-01-06'])
        self.assertEqual(len(r['rows']),1)
        self.assertEqual(r['excluded_dates'],['2026-01-05'])
