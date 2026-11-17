import unittest
from test_v033 import fixture
from score import evaluate


class BalanceVerification(unittest.TestCase):
    def test_issuer_other_liability_loan_disproves_net_cash(self):
        from financial_evidence import balance_bound
        d=self.data();d['as_of']='2025-04-30';d['code']='600608'
        d['bs'].update(statement_date='2024-12-31',cash=27191426.46,debt=10934850.94)
        d['balance_bound_verification']=balance_bound('600608','2024-12-31',d['as_of'])
        self.assertFalse(evaluate(d)['metrics']['net_cash'])
        self.assertIsNone(balance_bound('600608','2024-12-31','2025-04-29'))
        self.assertIsNone(balance_bound('600608','2025-12-31','2026-05-01'))
        for change in ({'debt_lower_bound':1},{'cash_upper_bound':1},
                       {'statement_date':'2023-12-31'},{'source':''},{'debt_lower_bound':float('inf')}):
            copy=dict(d['balance_bound_verification']);d['balance_bound_verification'].update(change)
            self.assertIsNone(evaluate(d)['metrics']['net_cash'])
            d['balance_bound_verification']=copy

    def data(self):
        d=fixture();d['balance_basis']='cash-debt-verification-v2';d['bs']['statement_date']='2025-12-31';return d
    def test_unverified_cash_does_not_earn_seven(self):
        d=self.data();old=fixture()
        self.assertEqual(evaluate(old)['安全']-evaluate(d)['安全'],7)
        self.assertIn('可用现金及完整债务',evaluate(d)['状态未知'])
    def test_verified_same_statement(self):
        d=self.data();d['balance_verification']=dict(available_cash=40e8,complete_interest_debt=1e8,statement_date='2025-12-31',available_date='2026-04-30',source='issuer-note-reference')
        self.assertTrue(evaluate(d)['metrics']['net_cash'])
    def test_future_or_wrong_statement_not_used(self):
        for changes in ({'available_date':'invalid'},{'available_date':'2026-06-01'},{'statement_date':'2024-12-31'},{'available_cash':60e8},{'source':''}):
            d=self.data();d['balance_verification']=dict(available_cash=40e8,complete_interest_debt=1e8,statement_date='2025-12-31',available_date='2026-04-30',source='issuer-note-reference',**{})
            d['balance_verification'].update(changes)
            self.assertIsNone(evaluate(d)['metrics']['net_cash'])

    def test_nonfinite_and_boolean_unknown(self):
        from rules import _n
        for value in (float('inf'),float('nan'),True):
            self.assertIsNone(_n(value))

    def test_unverified_noncash_dilution_not_awarded(self):
        d=self.data()
        self.assertIsNone(evaluate(d)['metrics']['invest_vs_paid'])
        self.assertEqual(evaluate(fixture())['回报']-evaluate(d)['回报'],5)

    def test_financing_evidence_same_window(self):
        d=self.data();d['financing_verification']=dict(parent_equity_financing=1e8,complete=True,
            includes_noncash=True,excludes_minority=True,source='issuance-event-ledger',
            start_year=2020,end_year=2024,available_date='2026-04-30')
        self.assertTrue(evaluate(d)['metrics']['invest_vs_paid'])
        d['financing_verification']['end_year']=2025
        self.assertIsNone(evaluate(d)['metrics']['invest_vs_paid'])

    def test_financing_evidence_before_window_end_rejected(self):
        d=self.data();d['financing_verification']=dict(parent_equity_financing=0,complete=True,
            includes_noncash=True,excludes_minority=True,source='issuance-event-ledger',
            start_year=2020,end_year=2024,available_date='2023-12-31')
        self.assertIsNone(evaluate(d)['metrics']['invest_vs_paid'])

    def test_negative_complete_debt_not_verified(self):
        d=self.data();d['bs']['debt']=-100
        d['balance_verification']=dict(available_cash=0,complete_interest_debt=-1,
            statement_date='2025-12-31',available_date='2026-04-30',source='bad-amount')
        self.assertIsNone(evaluate(d)['metrics']['net_cash'])
