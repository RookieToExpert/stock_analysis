import unittest
from eligibility_audit import eligibility


def sample():return {'basic':[{'ipoDate':'2015-05-06','outDate':''}],'daily':[{'date':'2020-05-06','isST':'0'}]}


class Eligibility(unittest.TestCase):
    def test_terminal_notices_and_jinshi_release(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        stocks = json.loads((root/'results/pit-evidence-2026-11-18/st-followup/inputs.json').read_text())
        days = {
            'sz.002477': '2019-09-02', 'sh.600074': '2020-05-06', 'sh.600891': '2021-05-06',
            'sz.002450': '2021-05-06', 'sz.002071': '2021-05-06', 'sz.002260': '2022-05-05',
            'sz.000585': '2022-05-05', 'sh.603996': '2022-05-05', 'sz.000835': '2022-05-05',
            'sz.002951': '2026-09-01',
        }
        self.assertEqual({stock['code'] for stock in stocks}, set(days))
        for stock in stocks:
            code = stock['code']
            with self.subTest(code=code):
                # A future delisting date is unnecessary for a decision already disclosed at the time.
                stock['basic'][0]['outDate'] = ''
                if code == 'sz.002951':
                    for day in ('2025-05-23', '2025-09-01', '2026-05-06', days[code]):
                        self.assertEqual(eligibility(stock, day), (True, 'age_ST_pass'))
                else:
                    reason = 'awaiting_delisting_after_final_trade' if code == 'sh.600891' else 'delisting_period'
                    self.assertEqual(eligibility(stock, days[code]), (False, reason))

    def test_delisting_evidence_respects_bounds_publication_and_final_trade(self):
        import copy
        import json
        from pathlib import Path
        from unittest.mock import patch
        from eligibility_audit import delisting_periods, delisting_reason
        root = Path(__file__).resolve().parents[1]
        stocks = json.loads((root/'results/pit-evidence-2026-11-18/st-followup/inputs.json').read_text())
        stock = next(s for s in stocks if s['code'] == 'sh.600891')
        proof = next(p for p in delisting_periods() if p['code'] == stock['code'])
        flag = '2021-03-19'
        self.assertIsNone(delisting_reason(stock, flag, '2021-03-18'))
        self.assertIsNone(delisting_reason(stock, flag, '2021-05-13'))
        for patch_value in ({'available_date': '2021-05-06'}, {'source_text_sha256': 'changed'}):
            with patch('eligibility_audit.delisting_periods', return_value=[{**proof, **patch_value}]):
                self.assertIsNone(delisting_reason(stock, flag, '2021-05-06'))
        for date, status in (('2021-04-30', '0'), ('2021-05-06', '1')):
            other = copy.deepcopy(stock)
            next(row for row in other['daily'] if row['date'] == date)['tradestatus'] = status
            self.assertIsNone(delisting_reason(other, flag, '2021-05-06'))
        other = copy.deepcopy(stock)
        other['daily'] = [r for r in other['daily'] if r['date'] != '2021-04-30']
        self.assertIsNone(delisting_reason(other, flag, '2021-05-06'))

    def test_delayed_confirmation_is_usable_only_after_publication_and_with_matching_bars(self):
        import copy
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root/'results/pit-evidence-2026-11-18/haiyuan-input.json').read_text())
        for day in ('2021-06-22', '2021-06-23', '2021-07-01', '2021-07-02'):
            self.assertEqual(eligibility(data, day), (None, 'ST_release_requires_issuer_evidence'))
        self.assertEqual(eligibility(data, '2021-07-05'), (True, 'age_ST_pass'))
        for changed_day, status in (('2021-06-22', '1'), ('2021-06-23', '0')):
            changed = copy.deepcopy(data)
            next(row for row in changed['daily'] if row['date'] == changed_day)['tradestatus'] = status
            self.assertIsNone(eligibility(changed, '2021-07-05')[0])

    def test_day_specific_gap_list_separates_missing_file_field_and_release(self):
        import csv
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from eligibility_audit import audit, write_gap_csv
        from test_pit_audit import sample as complete_years
        day = '2025-05-06'
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'universe.json').write_text(json.dumps({day:['sh.600900','sz.000002','sz.000003'], '2017-05-02':[]}))
            d = {**complete_years(), 'basic':[{'ipoDate':'1999-01-01'}], 'code':'sh.600900',
                 'daily':[{'date':day,'isST':'0'}]}
            d['fin']['cash'][-1]['CFOToNP'] = ''
            (root/'sh.600900.json').write_text(json.dumps(d))
            d.update(code='sz.000002', daily=[{'date':'2025-04-30','isST':'1'}, {'date':day,'isST':'0'}])
            (root/'sz.000002.json').write_text(json.dumps(d))
            report = audit(root, day)['evaluations']
            self.assertEqual(list(report), [day])
            self.assertEqual(len(report[day]['unknown_eligibility']), 2)
            output = root/'gaps.csv'
            write_gap_csv(report, output)
            with output.open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.reader(handle))[1:]
            self.assertEqual(rows, [[day,'sh.600900','财报','2024-12-31','cash','CFOToNP'],
                                    [day,'sz.000002','摘帽公告',day,'daily','isST']])
            with self.assertRaises(ValueError):
                audit(root,'2020-01-01')

    def test_eight_real_releases_have_contemporaneous_issuer_evidence(self):
        import gzip,json
        from pathlib import Path
        from eligibility_audit import release_ledger,verified_release
        root=Path(__file__).resolve().parents[1]
        with gzip.open(root/'results/st-source-audit-2026-11-17/release-inputs.json.gz','rt') as f:inputs=json.load(f)
        for data in inputs:
            day=max(r['date'] for r in data['daily'])
            with self.subTest(code=data['code']):
                self.assertEqual(eligibility(data,day),(True,'age_ST_pass'))
                proof=verified_release(data['code'],day)
                self.assertLessEqual(proof['available_date'],day)
                self.assertFalse(verified_release(data['code'],'1900-01-01'))
        self.assertEqual(len(inputs),8)

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
