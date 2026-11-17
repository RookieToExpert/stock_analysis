import gzip
import json
import unittest
from historical_industry import ROOT,lookup,parse_table,manifest


class HistoricalIndustry(unittest.TestCase):
    def test_publication_date_not_observation_period_controls_availability(self):
        self.assertIsNone(lookup('600608','2017-02-16'))
        self.assertEqual(lookup('600608','2017-05-02')['major'],'31')
        self.assertEqual(lookup('600608','2021-04-14')['major'],'31')
        self.assertEqual(lookup('600608','2021-04-15')['major'],'51')
        self.assertEqual(lookup('000001','2024-02-08')['taxonomy'],'CSRC2012')
        self.assertEqual(lookup('000001','2024-02-09')['taxonomy'],'CAPCO2023')
        self.assertEqual(lookup('000001','2026-09-30')['period'],'2025H2')
        self.assertEqual(lookup('000001','2026-10-01')['period'],'2026H1')
        self.assertTrue(lookup('000001','2017-05-02')['financial'])
        self.assertFalse(lookup('600519','2017-05-02')['financial'])

    def test_official_duplicate_code_is_unknown_not_last_row_wins(self):
        self.assertIsNone(lookup('603026','2017-06-02'))
        self.assertIsNone(lookup('999999','2026-10-01'))
        result=parse_table(' 26 化工 603026 石大胜华\n 33 金属 603026 科森科技')
        self.assertNotIn('603026',result['rows'])
        self.assertIn('603026',result['ambiguous_codes'])

    def test_both_official_sort_orders_agree_for_all_seven_modern_tables(self):
        checked=0
        for meta in manifest():
            if meta['taxonomy']!='CAPCO2023':continue
            source=json.loads((ROOT/(meta['period']+'.json')).read_text())
            doc=next(d for d in source['documents'] if '行业排序' in d.get('label',''))
            with gzip.open(ROOT/(doc['key']+'.txt.gz'),'rt') as f:other=parse_table(f.read())['rows']
            with gzip.open(ROOT/meta['file'],'rt') as f:main=json.load(f)
            self.assertEqual({k:v['major'] for k,v in other.items()},{k:v['major'] for k,v in main.items()})
            checked+=1
        self.assertEqual(checked,7)
