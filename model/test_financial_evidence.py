import copy
from datetime import date, timedelta
import json
from pathlib import Path
import unittest
from financial_evidence import verified_operating_cash_flow, default_ledger
from pit_audit import annual_missing

ROOT=Path(__file__).resolve().parents[1]


class FinancialEvidence(unittest.TestCase):
    def test_five_year_parent_financing_requires_every_year_and_matching_window(self):
        from financial_evidence import financing_evidence
        proof=financing_evidence('600608',2020,2024,'2025-07-01')
        self.assertEqual(proof['parent_equity_financing'],0)
        self.assertTrue(proof['includes_noncash'])
        self.assertIsNone(financing_evidence('600608',2021,2025,'2026-07-01'))
        self.assertIsNone(financing_evidence('600608',2020,2024,'2025-04-29'))
        for kind in ('missing_year','future','changed_hash','wrong_amount','offsetting_negative'):
            bad=copy.deepcopy(proof)
            if kind=='missing_year':bad['annual_evidence'].pop()
            if kind=='future':bad['annual_evidence'][0]['available_date']='2026-01-01'
            if kind=='changed_hash':bad['annual_evidence'][0]['source_text_sha256']='changed'
            if kind=='wrong_amount':bad['parent_equity_financing']=1
            if kind=='offsetting_negative':
                bad['annual_evidence'][0]['parent_cash_equity_financing']='-1'
                bad['annual_evidence'][1]['parent_cash_equity_financing']='1'
            self.assertIsNone(financing_evidence('600608',2020,2024,'2025-07-01',[bad]))

    def setUp(self):
        self.inputs=json.loads((ROOT/'results/financial-field-audit-2026-11-17/missing-cash-inputs.json').read_text())

    def test_six_real_missing_ratios_use_dated_direct_amounts_without_mutation(self):
        for data,fix in zip(self.inputs,default_ledger()):
            original=copy.deepcopy(data)
            pub=date.fromisoformat(fix['available_date']);day=(pub+timedelta(days=1)).isoformat()
            self.assertIsNone(verified_operating_cash_flow(data,fix['statDate'],pub.isoformat()))
            proof=verified_operating_cash_flow(data,fix['statDate'],day)
            self.assertEqual(proof['amount'],float(fix['value']))
            self.assertEqual(data,original)
            self.assertNotIn('cash:'+fix['statDate']+':CFOToNP',annual_missing(data,day))
        self.assertEqual(len(self.inputs),6)

    def test_changed_version_duplicate_rows_or_new_provider_ratio_not_overridden(self):
        for kind in ('profit','cash_date','duplicate','ratio','code'):
            data=copy.deepcopy(self.inputs[0]);period=data['fin']['cash'][0]['statDate']
            if kind=='profit':data['fin']['profit'][0]['netProfit']='123'
            if kind=='cash_date':data['fin']['cash'][0]['pubDate']='2025-04-27'
            if kind=='duplicate':data['fin']['profit']*=2
            if kind=='ratio':data['fin']['cash'][0]['CFOToNP']='0.5'
            if kind=='code':data['code']='sh.999999'
            self.assertIsNone(verified_operating_cash_flow(data,period,'2025-05-01'))

    def test_missing_source_nonfinite_wrong_basis_and_hash_refused(self):
        data=self.inputs[0];period=data['fin']['cash'][0]['statDate']
        for patch in ({'source':''},{'value':'NaN'},{'source_text_sha256':'changed'},
                      {'statement_basis':'parent_cash_flow'},{'available_date':'bad-date'}):
            ledger=copy.deepcopy(default_ledger());ledger[0].update(patch)
            self.assertIsNone(verified_operating_cash_flow(data,period,'2025-05-01',ledger))
