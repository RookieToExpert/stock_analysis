import unittest
from eligibility_audit import eligibility


def sample():return {'basic':[{'ipoDate':'2015-05-06','outDate':''}],'daily':[{'date':'2020-05-06','isST':'0'}]}


class Eligibility(unittest.TestCase):
    def test_anniversary(self):self.assertTrue(eligibility(sample(),'2020-05-06')[0])
    def test_too_young(self):self.assertFalse(eligibility(sample(),'2020-05-05')[0])
    def test_st(self):
        d=sample();d['daily'][0]['isST']='1';self.assertFalse(eligibility(d,'2020-05-06')[0])
    def test_missing_state_unknown(self):
        d=sample();d['daily']=[];self.assertIsNone(eligibility(d,'2020-05-06')[0])
