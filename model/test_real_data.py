"""用真实接口快照验证字段、单位和年报核对值。"""
import json
import unittest
from pathlib import Path
from rules import metrics, missing_fields
from score import BS_FIELDS, CF_FIELDS, MAIN_FIELDS, evaluate

FIX = Path(__file__).parent / "fixtures"


def load(code):
    return json.loads((FIX / f"{code}.json").read_text())


class Real(unittest.TestCase):
    def test_600900_matches_annual_report(self):
        d = load("600900")
        y = {r["year"]: r for r in d["years"]}
        self.assertAlmostEqual(y["2025"]["paid"], 23073529306.19, places=2)
        cf = d["source"]["cash_flow"][0]
        self.assertAlmostEqual(cf["ASSIGN_DIVIDEND_PORFIT"], 34191120693.30, places=2)
        self.assertAlmostEqual(cf["SUBSIDIARY_PAY_DIVIDEND"], 649469714.09, places=2)

    def test_600900_payout_is_not_interest_polluted(self):
        self.assertAlmostEqual(metrics(load("600900"))["payout"], 68.3, places=1)

    def test_real_fields_are_complete(self):
        for code in ("600900", "002749"):
            d = load(code)
            self.assertEqual(missing_fields(d), [])
            for rows, fields in ((d["source"]["main"], MAIN_FIELDS), (d["source"]["cash_flow"], CF_FIELDS), (d["source"]["balance"], BS_FIELDS)):
                self.assertTrue(set(fields) <= set(rows[0]))

    def test_market_cap_is_yuan(self):
        self.assertGreater(load("600900")["mv"], 1e11)

    def test_quarter_report_ttm(self):
        d = load("002749")
        self.assertTrue(d["source"]["main"][0]["REPORT_DATE"].startswith("2026-09-30"))
        self.assertAlmostEqual(d["ttm_np"] / 1e8, 2.39, places=1)

    def test_002749_review_state(self):
        r = evaluate(load("002749"))
        self.assertEqual((r["总分"], r["等级"], r["动作"]), (92, "合格", "事件复核"))


if __name__ == "__main__":
    unittest.main()
