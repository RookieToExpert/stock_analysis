import unittest
from issuer_sampling import latest_listed_annual


class IssuerSampling(unittest.TestCase):
    def test_post_delisting_and_later_downloads_cannot_shift_frozen_sample(self):
        d={'basic':[{'ipoDate':'2000-01-01','outDate':'2021-03-03'}], 'fin':{'profit':[
            {'statDate':'2019-12-31','pubDate':'2020-04-30'},
            {'statDate':'2020-12-31','pubDate':'2021-04-30'},
            {'statDate':'2022-12-31','pubDate':'2023-04-30'}]}}
        self.assertEqual(latest_listed_annual(d,'2026-11-17','2022-12-31')['statDate'],'2019-12-31')
        d['basic'][0]['outDate']=''
        self.assertEqual(latest_listed_annual(d,'2026-11-17','2020-12-31')['statDate'],'2020-12-31')
        self.assertIsNone(latest_listed_annual(d,'2020-04-30','2020-12-31'))
        d['fin']['profit'].append({'statDate':'2020-12-31','pubDate':'2021-05-01'})
        with self.assertRaises(ValueError):latest_listed_annual(d,'2026-11-17','2020-12-31')
