import unittest
from calendar_coverage import calendar_gap_reason


class Coverage(unittest.TestCase):
    def test_structural_and_unexplained_gaps(self):
        cal=dict(start='2020-01-02',end='2020-01-06',dates=['2020-01-02','2020-01-03','2020-01-06'])
        d={'basic':[{'ipoDate':'2020-01-03'}],'daily':[{'date':'2020-01-03'}]}
        self.assertEqual(calendar_gap_reason(d,cal),'listed_after_window_start')
        d['basic']=[{'outDate':'2020-01-03'}]
        self.assertEqual(calendar_gap_reason(d,cal),'delisted_before_window_end')
        d['basic']=[{'outDate':'2020-01-07'}]
        self.assertEqual(calendar_gap_reason(d,cal),'incomplete_calendar_unexplained')
        d['daily']*=2
        self.assertEqual(calendar_gap_reason(d,cal),'duplicate_daily_dates')
        d['daily']=[{'date':v} for v in cal['dates']]
        self.assertIsNone(calendar_gap_reason(d,cal))
