import unittest
from pit_audit import annual_missing,REQUIRED


def sample():
    return {'fin':{k:[dict(statDate=f'{y}-12-31',pubDate=f'{y+1}-04-30',**{f:'1' for f in fields}) for y in range(2020,2025)] for k,fields in REQUIRED.items()}}


class PITCoverage(unittest.TestCase):
    def test_complete(self): self.assertEqual(annual_missing(sample(),'2025-05-06'),[])
    def test_future_not_used(self):
        d=sample();d['fin']['profit'][-1]['pubDate']='2025-05-06'
        self.assertTrue(annual_missing(d,'2025-05-06'))
    def test_missing_field_not_zero(self):
        d=sample();d['fin']['profit'][0]['MBRevenue']=''
        self.assertTrue(annual_missing(d,'2025-05-06'))
    def test_ambiguous_revision_rejected(self):
        d=sample();d['fin']['profit'].append(d['fin']['profit'][0])
        self.assertTrue(annual_missing(d,'2025-05-06'))
