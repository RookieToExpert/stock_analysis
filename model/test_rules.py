import unittest
from rules import (action, recent_from_rows, blue_chip, clean_years, grade, metrics, missing_fields, recent_state,
                   score, state_unknown, vetoes, warnings)


def yr(year=2025, **k):
    b = dict(year=str(year), rev=100, np=20, np_all=21, kf=19, roe=18, gm=45, ocf=25, capex=5, invest=0, paid=10)
    return {**b, **k}


def years(n=5, **k):
    return [yr(2025 - i, **k) for i in range(n)]


def base(**k):
    d = dict(code="1", name="好公司", industry="化学制品", mv=300e8, ttm_np=20e8, price=90, high36=100, vol=20,
             kf_yoy=1, gm_delta=0, years=[yr(2025 - i, np=20e8, np_all=21e8, kf=19e8, ocf=25e8, capex=5e8, paid=10e8, rev=100e8) for i in range(5)],
             bs=dict(equity=100e8, assets=130e8, liab=30e8, cash=50e8, debt=0, goodwill=2e8))
    return {**d, **k}


def row(date, kf=100, gm=40):
    return {"REPORT_DATE": f"{date} 00:00:00", "KCFJCXSYJLR": kf, "XSMLL": gm}


class Recent(unittest.TestCase):
    def test_q3_ttm_and_yoy(self):
        rows = [row("2026-09-30", 80, 38), row("2025-12-31", 150, 40), row("2025-09-30", 100, 41)]
        ttm, yoy, gm = recent_from_rows(rows)
        self.assertEqual(ttm, 130)
        self.assertAlmostEqual(yoy, -20)
        self.assertAlmostEqual(gm, -3)

    def test_annual_uses_annual_value(self):
        self.assertEqual(recent_from_rows([row("2025-12-31", 150), row("2024-12-31", 100)])[0], 150)

    def test_misaligned_period_returns_none(self):
        ttm, yoy, gm = recent_from_rows([row("2026-09-30"), row("2025-12-31"), row("2025-06-30")])
        self.assertIsNone(ttm)
        self.assertIsNone(yoy)
        self.assertIsNone(gm)

    def test_loss_base_has_no_yoy(self):
        self.assertIsNone(recent_from_rows([row("2025-12-31", 50), row("2024-12-31", -10)])[1])


class Missing(unittest.TestCase):
    def test_empty_balance_sheet_no_safety_points_and_not_qualified(self):
        d = base(bs={})
        m = metrics(d)
        self.assertEqual(score(m)["安全"], 0)
        self.assertIsNone(m["net_cash"])
        self.assertEqual(grade(score(m)["总分"], vetoes(d, m), missing_fields(d)), "数据不足")

    def test_partial_balance_sheet(self):
        d = base(bs=dict(assets=130, equity=100, cash=50))
        m = metrics(d)
        self.assertIsNone(m["debt_ratio"])
        self.assertIsNone(m["gw_ratio"])
        self.assertEqual(score(m)["安全"], 0)
        self.assertIn("资产负债表缺goodwill", missing_fields(d))

    def test_real_zero_debt_is_scored(self):
        self.assertEqual(score(metrics(base()))["安全"], 20)

    def test_one_year_roe_does_not_count(self):
        ys = years(1, roe=30) + [yr(2024 - i, roe=None) for i in range(4)]
        m = metrics(base(years=ys))
        self.assertIsNone(m["roe_med"])
        self.assertIn("roe缺4年", missing_fields(base(years=ys)))

    def test_mismatched_cash_flow_year(self):
        ys = years(5)
        ys[2]["ocf"] = None
        self.assertIsNone(metrics(base(years=ys))["ocf_np"])

    def test_missing_ttm_removes_sustainable_yield(self):
        d = base(ttm_np=None)
        self.assertIsNone(metrics(d)["sust_yield"])
        self.assertIn("缺TTM利润", missing_fields(d))

    def test_missing_net_profit_is_not_a_pass(self):
        d = base(years=[yr(2025, np=None)] + [yr(2024 - i) for i in range(4)])
        self.assertIn("np缺1年", missing_fields(d))

    def test_gap_years_and_duplicates(self):
        y = clean_years([yr(2025), yr(2025), yr(2024), yr(2022), yr(2021), yr(2020)])
        self.assertEqual([r["year"] for r in y], ["2025", "2024"])
        self.assertFalse(metrics(base(years=y))["full"])


class Rules(unittest.TestCase):
    def test_good_company(self):
        d = base()
        m = metrics(d)
        self.assertEqual(vetoes(d, m), [])
        self.assertEqual(missing_fields(d), [])
        self.assertEqual(grade(score(m)["总分"], [], []), "合格")

    def test_ocf_uses_consolidated_profit(self):
        d = base(years=[yr(2025 - i, np=10, np_all=20, ocf=20) for i in range(5)])
        self.assertAlmostEqual(metrics(d)["ocf_np"], 1.0)

    def test_payout_uses_real_dividend(self):
        d = base(years=[yr(2025 - i, np=100, paid=68) for i in range(5)])
        self.assertAlmostEqual(metrics(d)["payout"], 68)

    def test_zero_dividend_is_known_not_missing(self):
        d = base(years=[yr(2025 - i, paid=0) for i in range(5)])
        m = metrics(d)
        self.assertEqual(m["paid_years"], 0)
        self.assertEqual(m["payout"], 0)
        self.assertEqual(missing_fields(d), [])
        self.assertEqual(m["sust_yield"], 0)

    def test_one_year_without_dividend_loses_points(self):
        ys = years(5)
        ys[1]["paid"] = 0
        self.assertEqual(metrics(base(years=ys))["paid_years"], 4)

    def test_loss_st_financial(self):
        d = base(name="*ST测试", industry="银行Ⅱ", years=[yr(2025, np=-5)] + [yr(2024 - i) for i in range(4)])
        v = vetoes(d, metrics(d))
        self.assertEqual(set(v), {"ST/退市风险", "金融股需单独建模", "近3年或TTM亏损"})

    def test_sustainable_yield_capped_by_ttm(self):
        d = base(ttm_np=3e8, mv=100e8)
        self.assertAlmostEqual(metrics(d)["sust_yield"], 3.0)

    def test_state_boundaries(self):
        self.assertEqual(recent_state(metrics(base(kf_yoy=-19.9, gm_delta=-2.9, high36=128))), [])
        self.assertEqual(len(recent_state(metrics(base(kf_yoy=-20, gm_delta=-3, high36=129)))), 3)

    def test_state_unknown_is_reported(self):
        self.assertEqual(state_unknown(metrics(base(kf_yoy=None, high36=None))), ["kf_yoy", "drawdown"])

    def test_warning_is_separate_from_deterioration(self):
        d = base(bs=dict(equity=100, assets=200, liab=100, cash=60, debt=50, goodwill=0))
        m = metrics(d)
        self.assertEqual(recent_state(m), [])
        self.assertEqual(warnings(m), ["存贷双高"])
        self.assertEqual(action("合格", [], warnings(m), []), "人工补查")

    def test_action(self):
        self.assertEqual(action("合格", ["利润下滑"], [], []), "事件复核")
        self.assertEqual(action("合格", [], [], ["回撤"]), "人工补查")
        self.assertEqual(action("合格", [], [], []), "人工排雷")
        self.assertEqual(action("观察", ["x"], [], []), "不操作")

    def test_st_name_variants(self):
        for name in ("ST测试", "*ST测试", "S*ST测试", "PT金田A", "测试退"):
            d = base(name=name)
            self.assertIn("ST/退市风险", vetoes(d, metrics(d)), name)

    def test_grade(self):
        self.assertEqual(grade(95, ["x"], []), "出局")
        self.assertEqual(grade(95, [], ["缺"]), "数据不足")
        self.assertEqual(grade(75, [], []), "合格")
        self.assertEqual(grade(60, [], []), "观察")
        self.assertEqual(grade(59, [], []), "放弃")

    def test_blue_chip(self):
        m = metrics(base(years=[yr(2025 - i, np=100, paid=50) for i in range(5)]))
        self.assertTrue(blue_chip(200e8, m))
        self.assertFalse(blue_chip(199e8, m))
        over = metrics(base(years=[yr(2025 - i, np=100, paid=81) for i in range(5)]))
        self.assertFalse(blue_chip(300e8, over))


if __name__ == "__main__":
    unittest.main()
