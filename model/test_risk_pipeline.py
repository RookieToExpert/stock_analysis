import gzip,json,tempfile,unittest
from pathlib import Path
from risk_pipeline import parse_plan,action_rows,reconstruct
from total_return import CoverageError
from report import split
from test_report import r


class Pipeline(unittest.TestCase):
    def test_plan(self):
        x=parse_plan('10转2送1派4.3元')
        self.assertEqual(float(x['dividCashPsBeforeTax']),.43)
        self.assertEqual(float(x['dividStocksPs']),.1)
        self.assertEqual(float(x['dividReserveToStockPs']),.2)
    def test_ambiguous(self):
        for text in ('10配2股','10派4元另行说明','0派1元','10派1派2','10送2元'):
            with self.assertRaises(CoverageError):parse_plan(text)
    def test_future(self):
        rows=[dict(EX_DIVIDEND_DATE='2026-10-23',NOTICE_DATE='2026-10-24',ASSIGN_PROGRESS='实施方案',IMPL_PLAN_PROFILE='10派4.3元')]
        with self.assertRaises(CoverageError):action_rows(rows,'601919','2026-11-16','2023-10-31','2026-10-30')
    def test_missing_day_rejected(self):
        root=Path(__file__).parent/'fixtures/total_return'
        d=json.loads(gzip.decompress((root/'sh.600900.json.gz').read_bytes()))
        dates=sorted(x['date'] for x in d['daily']);cal=dict(start=dates[0],end=dates[-1],dates=dates)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'sh.600900.json';p.write_text(json.dumps(d))
            result=reconstruct('600900','2026-11-16',[],cal,temp)
            self.assertEqual(result['status'],'reconstructed')
            d['daily'].pop(10);p.write_text(json.dumps(d))
            with self.assertRaises(CoverageError):reconstruct('600900','2026-11-16',[],cal,temp)
    def test_proxy_not_used_in_pool(self):
        a=r('a',vol=100);a['risk_eligible']=False
        b=r('b',vol=10);b['risk_eligible']=True
        main,other,cut=split([a,b])
        self.assertEqual([x['code'] for x in main],['b']);self.assertEqual(cut,10)
        self.assertEqual([x['code'] for x in other],['a'])
    def test_decimal_cash_does_not_create_fake_conflict(self):
        self.assertEqual(parse_plan('10派4.4元')['dividCashPsBeforeTax'],'0.44')
    def test_default_fetch_selects_reconstruction(self):
        from unittest.mock import patch
        from score import fetch,evaluate
        from test_real_data import load
        old=load('600900');source=old['source'];balance=dict(source['balance'][0],LEASE_LIAB=None)
        risk=dict(status='reconstructed',data_checks_passed=True,basis='gross-ex-date-close-reinvestment-v1',high36=1.2,vol=12,closes=[1,1.1],drawdown=8.3)
        quote={'f43':3000,'f58':'test','f116':7e11,'f127':'电力'}
        with patch('score.rows',side_effect=[source['main'],source['cash_flow'],[balance]]),patch('score.dividend_rows',return_value=source['dividends']),patch('score.current_risk',return_value=risk),patch('score.fetch_price_risk') as proxy:
            d=fetch('600900',quote)
            output=evaluate(d)
        self.assertTrue(output['risk_eligible'])
        self.assertEqual(output['metrics']['drawdown'],8.3)
        proxy.assert_not_called()
