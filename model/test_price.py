import unittest

from score import ratio_adjust, stats_from_daily


def series(closes, start=1):
    return [(f"2024-01-{i + start:02d}", c, c) for i, c in enumerate(closes)]


class RatioAdjust(unittest.TestCase):
    def test_no_event_is_raw(self):
        raw = series([10, 11, 12])
        self.assertEqual(ratio_adjust(raw, raw), raw)

    def test_cash_dividend_is_proportional_not_subtracted(self):
        # 第 3 天除息每股 2 元：前复权（算术）把前两天各减 2
        raw = series([10, 10, 8, 8])
        arith = series([8, 8, 8, 8])
        out = ratio_adjust(raw, arith)
        self.assertAlmostEqual(out[0][1], 10 * 0.8)
        self.assertAlmostEqual(out[3][1], 8)

    def test_high_dividend_history_not_crushed(self):
        # 两次每股分红 4 元：算术前复权把最早价压到 4，等比应为 20×0.8×0.75=12
        raw = series([20, 20, 16, 16, 16, 12, 12])
        arith = [(d, c - 4 if i < 2 else c, h - 4 if i < 2 else h) for i, (d, c, h) in enumerate(series([16, 16, 12, 12, 12, 12, 12]))]
        out = ratio_adjust(raw, arith)
        self.assertAlmostEqual(out[0][1], 20 * 0.8 * 0.75)
        self.assertAlmostEqual(out[-1][1], 12)

    def test_split_with_cash(self):
        # 10 派 1 元转 10 股：(原价 - 0.1) / 2
        raw = series([10.1, 10.3, 10.5, 5.0, 5.1])
        arith = [(d, round((c - 0.1) / 2, 2) if i < 3 else c, round((h - 0.1) / 2, 2) if i < 3 else h) for i, (d, c, h) in enumerate(raw)]
        out = ratio_adjust(raw, arith)
        self.assertAlmostEqual(out[2][1], 10.5 * (10.5 - 0.1) / 2 / 10.5, places=2)

    def test_mismatched_dates_or_unexplained_jump_is_unknown(self):
        self.assertIsNone(ratio_adjust(series([1, 2]), series([1, 2], start=2)))
        raw = series([10, 10.2, 10.4, 10.6, 5])
        arith = series([1, 7, 3, 9, 5])
        self.assertIsNone(ratio_adjust(raw, arith))

    def test_stats_from_daily(self):
        rows = [(f"{2023 + m // 12}-{m % 12 + 1:02d}-15", 10 + m % 3, 11 + m % 3) for m in range(40)]
        high, vol, closes = stats_from_daily(rows)
        self.assertEqual(len(closes), 37)
        self.assertEqual(high, 13)
        self.assertGreater(vol, 0)
        self.assertEqual(stats_from_daily(rows[:5])[:2], (None, None))


if __name__ == "__main__":
    unittest.main()
