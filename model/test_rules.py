import unittest
from rules import metrics, vetoes, warnings, recent_state, score, grade


def yr(**k):
    b = dict(rev=100, np=20, roe=18, gm=45, ocf=25, capex=5, invest=0, paid=10)
    return {**b, **k}


def base(**k):
    d = dict(name="好公司", industry="化学制品", mv=200, ttm_np=20, price=70, high36=100, years=[yr() for _ in range(5)],
             bs=dict(equity=100, assets=130, liab=30, cash=50, goodwill=2))
    return {**d, **k}


class T(unittest.TestCase):
    def test_good_company(self):
        m = metrics(base())
        self.assertEqual(vetoes(base(), m), [])
        self.assertEqual(round(m["drawdown"]), 30)
        self.assertGreaterEqual(score(m)["总分"], 75)

    def test_short_history_vetoed(self):
        d = base(years=[yr() for _ in range(3)])
        self.assertIn("年报不足5年", vetoes(d, metrics(d)))

    def test_missing_fields_score_zero_not_crash(self):
        d = base(mv=None, ttm_np=None, price=None, years=[yr(roe=None, gm=None, ocf=None, paid=None) for _ in range(5)], bs={})
        m = metrics(d)
        self.assertLess(score(m)["总分"], 25)
        self.assertIsNone(m["drawdown"])

    def test_loss_and_st(self):
        d = base(name="*ST测试", years=[yr(np=-5)] + [yr() for _ in range(4)])
        v = vetoes(d, metrics(d))
        self.assertIn("ST/退市风险", v)
        self.assertIn("近3年或TTM亏损", v)

    def test_financial_and_cash_debt(self):
        d = base(industry="银行Ⅱ", bs=dict(equity=100, assets=200, liab=100, cash=60, short_loan=50))
        v = vetoes(d, metrics(d))
        self.assertIn("金融股需单独建模", v)
        self.assertNotIn("存贷双高", v)
        self.assertIn("存贷双高", warnings(metrics(d)))

    def test_overpaying_dividend_loses_points(self):
        ok = score(metrics(base()))["回报"]
        over = score(metrics(base(years=[yr(paid=30) for _ in range(5)])))["回报"]
        self.assertLess(over, ok)

    def test_sustainable_yield_capped_by_ttm_profit(self):
        d = base(ttm_np=2, years=[yr(paid=30) for _ in range(5)])
        self.assertAlmostEqual(metrics(d)["sust_yield"], 1.0)

    def test_recent_deterioration_blocks_direct_buy(self):
        d = base(kf_yoy=-26, gm_delta=-3.3, high36=70)
        st = recent_state(metrics(d))
        self.assertEqual(len(st), 2)
        self.assertEqual(grade(92, [], st), "事件复核")

    def test_loss_base_year_has_no_yoy(self):
        self.assertEqual(recent_state(metrics(base(kf_yoy=None, high36=70))), [])

    def test_grade(self):
        self.assertEqual(grade(90, ["x"]), "出局")
        self.assertEqual(grade(90, [], [], ["存贷双高"]), "事件复核")
        self.assertEqual(grade(75, []), "候选")
        self.assertEqual(grade(60, []), "观察")
        self.assertEqual(grade(59, []), "放弃")


if __name__ == "__main__":
    unittest.main()
