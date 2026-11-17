import copy
import unittest
from historical_market_cap import calculate


class MarketCap(unittest.TestCase):
    def data(self):
        return {'code':'sh.600001','daily':[{'date':'2025-04-30','close':'10'},{'date':'2025-05-06','close':'99'}],
                'fin':{'profit':[{'code':'sh.600001','statDate':'2024-12-31','pubDate':'2025-04-29','totalShare':'1000000000'},
                                 {'code':'sh.600001','statDate':'2025-03-31','pubDate':'2025-04-28','totalShare':'2000000000'},
                                 {'code':'sh.600001','statDate':'2025-06-30','pubDate':'2025-08-28','totalShare':'3000000000'}]}}

    def test_newest_period_not_latest_publication_and_no_current_quote(self):
        d=self.data();original=copy.deepcopy(d);m=calculate(d,'2025-05-06')
        self.assertEqual(m['value_yuan'],20000000000)
        self.assertEqual(m['statement_date'],'2025-03-31')
        self.assertEqual(m['price_date'],'2025-04-30')
        self.assertFalse(m['effective_share_register_verified'])
        self.assertEqual(d,original)

    def test_same_day_report_duplicate_or_nonfinite_is_not_used(self):
        d=self.data();d['fin']['profit'][1]['pubDate']='2025-05-06'
        self.assertEqual(calculate(d,'2025-05-06')['shares'],'1000000000')
        for value in ('NaN','Infinity','-1','0',True):
            d=self.data();d['fin']['profit'][1]['totalShare']=value
            self.assertIsNone(calculate(d,'2025-05-06'))
        d=self.data();d['fin']['profit'].append(dict(d['fin']['profit'][1]))
        self.assertIsNone(calculate(d,'2025-05-06'))
