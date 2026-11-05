import unittest
from datetime import date
from backtest import Portfolio, at_limit, choose, dividend_tax_rate, fee, limit_pct, must_sell

D = date(2024, 1, 2)


def bar(open_=10.0, prev=10.0, **k):
    return {"open": open_, "prev_close": prev, **k}


class T(unittest.TestCase):
    def test_board_limits(self):
        self.assertEqual(limit_pct("600000", D), .10)
        self.assertEqual(limit_pct("300001", date(2020, 8, 23)), .10)
        self.assertEqual(limit_pct("300001", date(2020, 8, 24)), .20)
        self.assertEqual(limit_pct("688001", D), .20)

    def test_limit_detection(self):
        self.assertTrue(at_limit(bar(11, 10), "600000", D, True))
        self.assertTrue(at_limit(bar(9, 10), "600000", D, False))
        self.assertFalse(at_limit(bar(10.99, 10), "600000", D, True))

    def test_min_commission_and_stamp(self):
        self.assertAlmostEqual(fee(1000, False), 5.01)
        self.assertAlmostEqual(fee(1000, True), 5.51)
        self.assertAlmostEqual(fee(1000000, True), 250 + 10 + 500)

    def test_buy_rounds_to_lot_and_counts_cost(self):
        p = Portfolio(100000)
        p.buy(D, "600000", 10500, bar())
        self.assertEqual(p.shares("600000"), 1000)
        self.assertAlmostEqual(p.cash, 100000 - 10010 - fee(10010, False))

    def test_cash_cannot_go_negative(self):
        p = Portfolio(1003)
        p.buy(D, "600000", 1003, bar())
        self.assertEqual(p.shares("600000"), 0)
        self.assertEqual(p.log[-1]["status"], "资金不足一手")

    def test_limit_up_and_suspended_no_buy(self):
        p = Portfolio(100000)
        p.buy(D, "600000", 10000, bar(11, 10))
        p.buy(D, "600001", 10000, bar(suspended=True))
        self.assertEqual([x["status"] for x in p.log], ["涨停未成交", "停牌"])
        self.assertEqual(p.cash, 100000)

    def test_limit_down_defers_sell(self):
        p = Portfolio(100000)
        p.buy(D, "600000", 10000, bar())
        self.assertFalse(p.sell(D, "600000", bar(9, 10)))
        self.assertTrue(p.shares("600000") > 0)
        self.assertTrue(p.sell(D, "600000", bar(9.5, 9)))
        self.assertEqual(p.shares("600000"), 0)

    def test_dividend_tax_boundaries(self):
        self.assertEqual(dividend_tax_rate(D, date(2024, 2, 1)), .20)
        self.assertEqual(dividend_tax_rate(D, date(2024, 2, 2)), .10)
        self.assertEqual(dividend_tax_rate(D, date(2025, 1, 1)), .10)
        self.assertEqual(dividend_tax_rate(D, date(2025, 1, 2)), 0)

    def test_dividend_cash(self):
        p = Portfolio(100000)
        p.buy(D, "600000", 10100, bar())
        before = p.cash
        p.dividend(date(2024, 6, 1), "600000", 1)
        self.assertAlmostEqual(p.cash - before, 900)

    def test_split_and_delist(self):
        p = Portfolio(100000)
        p.buy(D, "600000", 10100, bar())
        p.split(date(2024, 5, 1), "600000", 1.2)
        self.assertEqual(p.shares("600000"), 1200)
        p.delist(date(2024, 8, 1), "600000", 1)
        self.assertEqual(p.shares("600000"), 0)
        self.assertEqual(p.log[-1]["action"], "delist")

    def test_value_requires_all_prices(self):
        p = Portfolio(100000)
        p.buy(D, "600000", 10000, bar())
        with self.assertRaises(ValueError):
            p.value({})

    def test_choose_industry_cap_and_top(self):
        cand = [str(i) for i in range(10)]
        ind = {c: "a" for c in cand}
        ind["9"] = "b"
        add, weight = choose(cand, [], ind)
        self.assertEqual(add, ["0", "1", "2", "3", "4", "9"])
        self.assertEqual(weight, .05)

    def test_choose_keeps_existing(self):
        add, _ = choose(["a", "b"], ["a"], {"a": "x", "b": "y"}, top=2)
        self.assertEqual(add, ["b"])

    def test_sell_rules(self):
        self.assertTrue(must_sell(["亏损"], 80, 0))
        self.assertTrue(must_sell([], 59, 0))
        self.assertTrue(must_sell([], 80, 2))
        self.assertFalse(must_sell([], 60, 1))


if __name__ == "__main__":
    unittest.main()
