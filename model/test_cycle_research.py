import unittest
from cycle_research import conservative_fcf
from test_rules import base


class Cycle(unittest.TestCase):
    def test_latest_downturn_not_hidden_by_average(self):
        d=base();d['years'][0]['capex']=30e8
        self.assertAlmostEqual(conservative_fcf(d),-5/300*100)
    def test_missing_unknown(self):
        d=base();d['years'][0]['ocf']=None
        self.assertIsNone(conservative_fcf(d))
    def test_constant_equal_baseline(self):
        self.assertAlmostEqual(conservative_fcf(base()),20/300*100)
