"""expiry_checker.find_stale_rows() の回帰テスト。

2026-08-12、「古いやつ消して全部新しい物件にしろ」という指示で手動一括処理した
「検出から3日超の提案済みを鮮度切れにする」処理を、check_expired_main.pyの
定期実行に組み込んで自動化した。閾値やプラットフォーム絞り込みが壊れると
Dispatchビューアに古い案件が溜まり続けるので、固定しておく。
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.expiry_checker import find_stale_rows


class TestFindStaleRows(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 8, 13)

    def test_old_row_is_stale(self):
        rows = [{"ステータス": "提案済み", "プラットフォーム": "CrowdWorks", "検出日": "2026-08-01"}]
        self.assertEqual(find_stale_rows(rows, {"crowdworks", "coconala"}, today=self.today), [2])

    def test_recent_row_is_not_stale(self):
        rows = [{"ステータス": "提案済み", "プラットフォーム": "CrowdWorks", "検出日": "2026-08-12"}]
        self.assertEqual(find_stale_rows(rows, {"crowdworks", "coconala"}, today=self.today), [])

    def test_non_proposed_status_ignored(self):
        rows = [{"ステータス": "未チェック", "プラットフォーム": "CrowdWorks", "検出日": "2026-08-01"}]
        self.assertEqual(find_stale_rows(rows, {"crowdworks", "coconala"}, today=self.today), [])

    def test_platform_filter(self):
        rows = [{"ステータス": "提案済み", "プラットフォーム": "ココナラ", "検出日": "2026-08-01"}]
        self.assertEqual(find_stale_rows(rows, {"crowdworks"}, today=self.today), [])
        self.assertEqual(find_stale_rows(rows, {"coconala"}, today=self.today), [2])

    def test_missing_detected_date_is_not_stale(self):
        rows = [{"ステータス": "提案済み", "プラットフォーム": "CrowdWorks", "検出日": ""}]
        self.assertEqual(find_stale_rows(rows, {"crowdworks", "coconala"}, today=self.today), [])


if __name__ == "__main__":
    unittest.main()
