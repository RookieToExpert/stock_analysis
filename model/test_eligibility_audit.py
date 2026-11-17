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
    def test_st_zero_does_not_prove_normal_listing(self):
        d=sample();d['daily'].insert(0,{'date':'2020-05-05','isST':'1'})
        self.assertEqual(eligibility(d,'2020-05-06'),(None,'ST_release_requires_issuer_evidence'))
        d['st_release_verification']={'source':'issuer announcement','effective_date':'2020-05-06',
                                     'available_date':'2020-05-05','status':'normal_listing'}
        self.assertTrue(eligibility(d,'2020-05-06')[0])
        d['st_release_verification']['available_date']='2020-05-07'
        self.assertIsNone(eligibility(d,'2020-05-06')[0])
    def test_future_st_cannot_change_past_eligibility(self):
        d=sample();d['daily'].append({'date':'2020-05-07','isST':'1'})
        self.assertTrue(eligibility(d,'2020-05-06')[0])
