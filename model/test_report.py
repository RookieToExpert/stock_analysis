import unittest
from report import split


def r(code, grade="合格", blue=True, vol=20, total=80, mv=300e8):
    return {"code": code, "等级": grade, "蓝筹条件": blue, "总分": total, "mv": mv, "metrics": {"vol": vol}}


class T(unittest.TestCase):
    def test_high_vol_blue_chip_moves_to_other(self):
        rows = [r(str(i), vol=10 + i) for i in range(10)]
        main, other, cut = split(rows)
        self.assertEqual(cut, 17)
        self.assertEqual(len(main), 8)
        self.assertEqual(len(other), 2)

    def test_non_blue_and_observe(self):
        main, other, _ = split([r("a", blue=False), r("b", grade="观察"), r("c")])
        self.assertEqual([x["code"] for x in main], ["c"])
        self.assertEqual([x["code"] for x in other], ["a"])

    def test_unknown_vol_is_not_main(self):
        main, other, _ = split([r("a", vol=None), r("b")])
        self.assertEqual([x["code"] for x in main], ["b"])
        self.assertEqual([x["code"] for x in other], ["a"])


if __name__ == "__main__":
    unittest.main()
