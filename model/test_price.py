import unittest

from score import ex_events, plan_terms, ratio_adjust, stats_from_daily


def series(closes):
    return [(f"2024-01-{i + 1:02d}", c, c) for i, c in enumerate(closes)]


class PlanTerms(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(plan_terms("10派2.5元"), (0.25, 0))
        self.assertEqual(plan_terms("10转2派2元"), (0.2, 0.2))
        self.assertEqual(plan_terms("10送1转2派3元(含税)"), (0.3, 0.3))
        self.assertEqual(plan_terms("10转增4股"), (0, 0.4))
        self.assertEqual(plan_terms("10送3"), (0, 0.3))
        self.assertIsNone(plan_terms("不分配不转增"))
        self.assertIsNone(plan_terms(""))

    def test_only_implemented_with_ex_date(self):
        rows = [{"IMPL_PLAN_PROFILE": "10派1元", "ASSIGN_PROGRESS": "实施方案", "EX_DIVIDEND_DATE": "2024-01-03 00:00:00"},
                {"IMPL_PLAN_PROFILE": "10派1元", "ASSIGN_PROGRESS": "股东大会预案", "EX_DIVIDEND_DATE": None},
                {"IMPL_PLAN_PROFILE": "10派1元", "ASSIGN_PROGRESS": "实施方案", "EX_DIVIDEND_DATE": None}]
        self.assertEqual(ex_events(rows), [("2024-01-03", 0.1, 0)])


class RatioAdjust(unittest.TestCase):
    def test_no_event_is_raw(self):
        raw = series([10, 11, 12])
        self.assertEqual(ratio_adjust(raw, []), raw)

    def test_cash_dividend_is_proportional_not_subtracted(self):
        out = ratio_adjust(series([10, 10, 8, 8]), [("2024-01-03", 2, 0)])
        self.assertAlmostEqual(out[0][1], 8)  # 10 × (10-2)/10
        self.assertAlmostEqual(out[3][1], 8)

    def test_high_dividend_history_not_crushed(self):
        # 两次每股 4 元：算术前复权最早价 20-8=12 已偏低到 60%；等比为 20×0.8×0.75=12，
        # 但最早价相对第一次除权前的高点比例保持不变
        out = ratio_adjust(series([20, 20, 16, 16, 16, 12, 12]), [("2024-01-03", 4, 0), ("2024-01-06", 4, 0)])
        self.assertAlmostEqual(out[0][1], 20 * 0.8 * 0.75)
        self.assertAlmostEqual(out[3][1], 16 * 0.75)
        self.assertAlmostEqual(out[-1][1], 12)

    def test_split_with_cash(self):
        # 10 转 2 派 2 元：ref = (11.86 - 0.2) / 1.2
        out = ratio_adjust(series([11.86, 9.9]), [("2024-01-02", 0.2, 0.2)])
        self.assertAlmostEqual(out[0][1], (11.86 - 0.2) / 1.2)

    def test_ex_date_on_non_trading_day_uses_next_trading_day(self):
        raw = [("2024-01-05", 10, 10), ("2024-01-08", 9, 9)]
        out = ratio_adjust(raw, [("2024-01-06", 1, 0)])
        self.assertAlmostEqual(out[0][1], 9)

    def test_future_and_old_events_ignored(self):
        raw = series([10, 10])
        self.assertEqual(ratio_adjust(raw, [("2030-01-01", 1, 0), ("2020-01-01", 1, 0)]), raw)

    def test_bad_reference_price_is_unknown(self):
        self.assertIsNone(ratio_adjust(series([1, 1]), [("2024-01-02", 5, 0)]))
        self.assertIsNone(ratio_adjust([], []))

    def test_stats_from_daily(self):
        rows = [(f"{2023 + m // 12}-{m % 12 + 1:02d}-15", 10 + m % 3, 11 + m % 3) for m in range(40)]
        high, vol, closes = stats_from_daily(rows)
        self.assertEqual(len(closes), 37)
        self.assertEqual(high, 13)
        self.assertGreater(vol, 0)
        self.assertEqual(stats_from_daily(rows[:5])[:2], (None, None))


if __name__ == "__main__":
    unittest.main()
