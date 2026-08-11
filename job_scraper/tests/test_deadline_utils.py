"""deadline_utils.normalize_deadline() の回帰テスト。

2026-08-11、CrowdWorksの「あと 2 日」（数字前後に半角スペース）が
スペース非対応の正規表現で一度も拾えていなかった（全期間0%）。
この関数はスクレイパー側で正規表現マッチした後のテキストを受け取る
想定なので、呼び出し側の正規表現がスペースを許容していることも
スクレイパー側のテストで別途担保する必要がある。
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.deadline_utils import normalize_deadline


class TestNormalizeDeadline(unittest.TestCase):
    def test_relative_days_no_space(self):
        self.assertEqual(normalize_deadline("あと2日", date(2026, 8, 11)), "2026-08-13")

    def test_relative_days_with_spaces(self):
        # CrowdWorksの実ページ表記（数字の前後に半角スペース）
        self.assertEqual(normalize_deadline("あと 2 日", date(2026, 8, 11)), "2026-08-13")

    def test_absolute_date_slash(self):
        self.assertEqual(normalize_deadline("2026/08/20", date(2026, 8, 11)), "2026-08-20")

    def test_absolute_date_dash(self):
        self.assertEqual(normalize_deadline("2026-08-20", date(2026, 8, 11)), "2026-08-20")

    def test_unknown(self):
        self.assertEqual(normalize_deadline("", date(2026, 8, 11)), "不明")
        self.assertEqual(normalize_deadline("応相談", date(2026, 8, 11)), "不明")


if __name__ == "__main__":
    unittest.main()
