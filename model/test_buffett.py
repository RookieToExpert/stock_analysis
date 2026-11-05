import unittest
from buffett import factors, pick, qv_pool, rank_qsc, ranks


def yr(year, **k):
    return {**dict(year=str(year), rev=100, np=20, np_all=21, kf=20, roic=12, roe=15, gm=40, ocf=25, capex=5, invest=0, paid=5), **k}


def data(**k):
    return {**dict(mv=1000, ttm_np=20, price=9, high36=10, vol=20, years=[yr(2025 - i) for i in range(5)],
                   bs=dict(assets=100, liab=30, equity=70, cash=10, debt=0, goodwill=0)), **k}


def row(code, industry="a", **k):
    return {**dict(code=code, industry=industry, mv=1, roic=10, ocf_np=1, retain=1, debt_ratio=30, vol=20, ep_norm=5, fcf_yield=5), **k}


class T(unittest.TestCase):
    def test_retained_return(self):
        d = data(years=[yr(2025, kf=30)] + [yr(2024 - i) for i in range(3)] + [yr(2021, kf=10)])
        self.assertAlmostEqual(factors(d)["retain"], 20 / 60)

    def test_negative_retained_is_unknown(self):
        self.assertIsNone(factors(data(years=[yr(2025 - i, paid=30) for i in range(5)]))["retain"])

    def test_missing_roic_is_unknown(self):
        self.assertIsNone(factors(data(years=[yr(2025, roic=None)] + [yr(2024 - i) for i in range(4)]))["roic"])

    def test_rank_direction_and_ties(self):
        rows = [row("a", vol=10), row("b", vol=20), row("c", vol=20)]
        low = ranks(rows, "vol", False)
        self.assertEqual(low["a"], 1)
        self.assertEqual(low["b"], low["c"])

    def test_equal_weight_score(self):
        rows = rank_qsc([row("a", roic=20, ocf_np=2, retain=2, debt_ratio=10, vol=10, ep_norm=9, fcf_yield=9), row("b")])
        self.assertEqual(rows[0]["score"], 1)
        self.assertEqual(rows[1]["score"], 0)

    def test_quality_gate(self):
        rows = [row("ok"), row("roic", roic=9.9), row("cash", ocf_np=.79), row("debt", debt_ratio=60.1)]
        self.assertEqual([r["code"] for r in qv_pool(rows)], ["ok"])

    def test_industry_cap(self):
        rows = [dict(row(str(i)), score=1 - i / 100) for i in range(6)] + [dict(row("x", "b"), score=.1)]
        self.assertEqual([r["code"] for r in pick(rows)], ["0", "1", "2", "3", "4", "x"])


if __name__ == "__main__":
    unittest.main()
