"""budget_utils.parse_budget_yen() の回帰テスト。

2026-08-11に同じ関数系統で3つの独立したバグ（範囲表記の上限握りつぶし、
千円/万円の位取り略記の未対応）が見つかったため、同じ失敗を将来また
静かに再発させないように固定した。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.budget_utils import parse_budget_yen


class TestParseBudgetYen(unittest.TestCase):
    def test_plain_value(self):
        self.assertEqual(parse_budget_yen("12,000円"), 12000)

    def test_range_uses_upper_bound(self):
        self.assertEqual(parse_budget_yen("30,000円 〜 50,000円"), 50000)
        self.assertEqual(parse_budget_yen("1,500円 〜 2,000円"), 2000)

    def test_man_shorthand(self):
        self.assertEqual(parse_budget_yen("10万円"), 100000)

    def test_sen_shorthand(self):
        self.assertEqual(parse_budget_yen("5千円未満"), 5000)

    def test_no_budget_info(self):
        self.assertIsNone(parse_budget_yen("見積り希望"))
        self.assertIsNone(parse_budget_yen(""))
        self.assertIsNone(parse_budget_yen("不明"))


if __name__ == "__main__":
    unittest.main()
