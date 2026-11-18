import copy
from decimal import Decimal
import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import annual_supplements as annual
from collect_gap_reports import report_kind
from explain_annual_gaps import explain
from financial_evidence import verified_operating_cash_flow
from historical_market_cap import calculate
from issuer_statements import Report
from pit_audit import REQUIRED, annual_missing
from reconcile_gap_reports import choose_source


def provider(code, period):
    record = annual.shard(code[:6])[code][period]
    tables = {}
    for table, pub in record['provider_dates'].items():
        row = {field: '' for field in REQUIRED[table]}
        row.update(record['anchors'].get(table, {}))
        tables[table] = [dict(row, code=code, statDate=period, pubDate=pub)]
    return {'code': code, 'fin': tables}


class AnnualSupplements(unittest.TestCase):
    def test_withdrawn_report_expires_until_a_verified_replacement_is_public(self):
        period = '2019-12-31'
        first = {'available_date': '2020-04-01', 'facts': {'operating_cash_flow': '1'}}
        amended = {'available_date': '2020-04-20', 'valid_through': '2020-04-29',
                   'facts': {'operating_cash_flow': '-2'}}
        replacement = {'available_date': '2020-05-05', 'facts': {'operating_cash_flow': '3'}}
        record = {'provider_dates': {}, 'anchors': {}, 'versions': [first, amended, replacement]}
        code = 'sh.600001'
        with patch.object(annual, 'shard', return_value={code: {period: record}}):
            stock = {'code':code,'fin':{}}
            for day, expected in [('2020-04-20', first), ('2020-04-29', amended), ('2020-04-30', None),
                                  ('2020-05-05', None), ('2020-05-06', replacement)]:
                with self.subTest(day=day):
                    self.assertEqual(annual.verified_annual_version(stock, period, day), expected)

    def test_inquiries_and_correction_announcements_are_not_replacement_financials(self):
        for title in ('对公司2019年年报的问询函的回复', '关于2019年年度报告及其摘要的更正公告',
                      '关于举行2019年年度报告网上说明会的通知'):
            self.assertEqual(report_kind(title, 2019, '2020-05-06'), 'notice')
        self.assertEqual(report_kind('2019年年度报告摘要（更新后）', 2019, '2020-05-06'), 'summary')

    def test_postponed_statements_require_actual_release_date_even_when_provider_has_values(self):
        period, code = '2019-12-31', 'sz.000667'
        tables = {table: [dict.fromkeys(fields, '1') | {'code': code, 'statDate': period, 'pubDate': '2020-04-30'}]
                  for table, fields in REQUIRED.items()}
        stock = {'code': code, 'fin': tables, 'daily': [{'date': '2020-06-05', 'close': '3'}]}
        for day in ('2020-05-06', '2020-06-06'):
            self.assertEqual({x for x in annual_missing(stock, day) if period in x},
                             {f'{t}:{period}:rows=0' for t in tables})
            self.assertIsNone(calculate(stock, day))
        self.assertFalse(any(period in x for x in annual_missing(stock, '2020-06-07')))
        self.assertEqual(calculate(stock, '2020-06-07')['publication_date'], '2020-06-06')
        state, detail, links = explain(code, period, '2020-05-06', 'cash', 'rows=0', None)
        self.assertEqual(state, '调仓日前尚未披露')
        self.assertIn('2020-06-06', detail)
        self.assertEqual(len(links), 2)

    def test_issuer_correction_changes_only_after_publication(self):
        period = '2022-12-31'
        stock = provider('sh.600165', period)
        old = verified_operating_cash_flow(stock, period, '2024-12-28')
        new = verified_operating_cash_flow(stock, period, '2024-12-29')
        self.assertEqual(old['amount'], 53144180.21)
        self.assertEqual(new['amount'], -33407119.79)
        self.assertNotEqual(old['evidence']['pdf_sha256'], new['evidence']['pdf_sha256'])
        self.assertIsNone(verified_operating_cash_flow(stock, period, '2023-04-28'))

    def test_consolidated_thousands_and_signed_outflows(self):
        period = '2023-12-31'
        data = provider('sh.600688', period)
        original = copy.deepcopy(data)
        cash = verified_operating_cash_flow(data, period, '2026-09-01')
        self.assertEqual(cash['amount'], 806996000)
        statement = cash['evidence']['evidence']['cash_statement']
        self.assertEqual(statement['page'], 99)
        self.assertEqual(Decimal(statement['inflow']) - Decimal(statement['outflow']), Decimal('806996000'))
        self.assertEqual(data, original)

    def test_ambiguous_or_changed_inputs_are_not_overridden(self):
        period, day = '2023-12-31', '2026-09-01'
        stock = provider('sh.600688', period)
        mutations = [('profit', 'netProfit', '3'), ('cash', 'pubDate', '2024-07-07'),
                     ('cash', 'code', 'sh.600001'), ('cash', 'CFOToNP', '0.4')]
        for table, field, value in mutations:
            changed = copy.deepcopy(stock)
            changed['fin'][table][0][field] = value
            self.assertIsNone(verified_operating_cash_flow(changed, period, day))
        stock['fin']['cash'] *= 2
        self.assertIsNone(verified_operating_cash_flow(stock, period, day))

    def test_missing_tables_require_all_semantic_inputs(self):
        period, day = '2022-12-31', '2026-09-01'
        stock = provider('sz.002555', period)
        version = annual.verified_annual_version(stock, period, day)
        self.assertEqual(version['facts']['MBRevenue'], '16406034152.65')
        self.assertEqual(set(version['facts']), set(REQUIRED['profit']))
        self.assertNotIn('profit:2022-12-31:rows=0', annual_missing(stock, day))
        stock['daily'] = [{'date': '2026-08-31', 'close': '10'}]
        self.assertEqual(calculate(stock, day)['shares'], '2217864281')
        stock['fin']['profit'] = [{'code': 'sh.600001', 'pubDate': '2023-04-28', 'statDate': period}]
        self.assertIsNone(annual.verified_annual_version(stock, period, day))
        self.assertIsNone(calculate(stock, day))

    def test_negative_equity_preserves_numerator_and_denominator(self):
        period, day = '2022-12-31', '2026-09-01'
        stock = provider('sh.600117', period)
        version = annual.verified_annual_version(stock, period, day)
        signed = Decimal(version['non_comparable']['roeAvg']['signed_formula_value'])
        self.assertGreater(signed, 0)
        proof = next(s for s in version['sources'] if s.get('non_comparable'))
        inputs = proof['evidence']['other_fields']
        self.assertLess(Decimal(inputs['average_parent_equity']), 0)
        self.assertEqual(signed, Decimal(inputs['parent']['value']) / Decimal(inputs['average_parent_equity']))
        self.assertIsNone(annual.field_value(version, 'roeAvg'))
        self.assertIn('profit:2022-12-31:roeAvg', annual_missing(stock, day))
        state, detail, links = explain(stock['code'], period, day, 'profit', 'roeAvg', version)
        self.assertEqual((state, detail), ('已核实但指标不可比', '平均归母净资产为负'))
        self.assertTrue(all('#page=' in link for link in links) and links)

    def test_subsidiary_with_parent_code_in_related_party_list_is_not_accepted(self):
        text = '2024年年度报告\n公司代码：000001\n关联公司 600001\n'
        self.assertFalse(Report(text, 'sh.600001', 2024).cover_ok)
        text = '2024年年度报告\n公司代码：600001\n上期比较数字来自2023年\n'
        self.assertFalse(Report(text, 'sh.600001', 2023).cover_ok)

    def test_same_day_audited_disagreement_stays_open(self):
        def source(link, amount):
            return {'facts': {'operating_cash_flow': amount}, 'source': link,
                    'cash_basis': 'consolidated_statement_and_subtotals',
                    'evidence': {'cash_statement': {'precision': '0.01'}}}
        self.assertIsNone(choose_source('operating_cash_flow', [source('a','11.10'), source('b','11.12')]))

    def test_predecessor_filings_require_dated_issuer_continuity(self):
        period = '2014-12-31'
        data = {'code':'sz.001872', 'fin':{}}
        self.assertIsNone(annual.verified_annual_version(data, period, '2018-12-26'))
        version = annual.verified_annual_version(data, period, '2018-12-27')
        self.assertEqual(version['facts']['totalShare'], '644763730')
        self.assertEqual(version['sources'][0]['issuer_code'], 'sz.000022')
        self.assertEqual(version['identity_available_date'], '2018-12-26')

    def test_no_business_revenue_and_undefined_gross_margin_are_distinct(self):
        period = '2012-12-31'
        stock = provider('sz.000030', period)
        version = annual.verified_annual_version(stock, period, '2017-05-02')
        self.assertEqual(annual.field_value(version, 'MBRevenue'), 0)
        self.assertIsNone(annual.field_value(version, 'gpMargin'))
        self.assertEqual(version['non_comparable']['gpMargin']['reason'], 'zero_operating_revenue')

    def test_scanned_update_keeps_the_signed_current_period_cash_amount(self):
        period = '2013-12-31'
        stock = provider('sh.600771', period)
        cash = verified_operating_cash_flow(stock, period, '2017-05-02')
        self.assertEqual(cash['amount'], -18795819.94)
        proof = cash['evidence']['evidence']['reviewed_fields']['operating_cash_flow']
        self.assertEqual(proof['page'], 8)
        self.assertEqual(proof['prior_year_amount'], '-19167624.89')

    def test_modified_evidence_shard_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'evidence').mkdir()
            content = gzip.compress(b'{}')
            (root/'evidence/sh.999.json.gz').write_bytes(content + b'changed')
            with patch.object(annual, 'EVIDENCE', root), patch.object(annual, 'bundle_index',
                      return_value={'sh.999': hashlib.sha256(content).hexdigest()}):
                self.assertEqual(annual.shard('sh.999'), {})
            annual.shard.cache_clear()
