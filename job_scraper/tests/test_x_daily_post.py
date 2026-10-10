import unittest
from datetime import datetime, timezone

from x_daily_post import image_for, load_posts, message, today_index


class XDailyPostTest(unittest.TestCase):
    def test_reads_posts_from_the_shared_file(self):
        js = 'var X_DAILY = [\n  "一つ目\\nの投稿",\n  "二つ目「です」",\n];\nfunction xTodayIndex() {}'
        self.assertEqual(load_posts(js), ["一つ目\nの投稿", "二つ目「です」"])

    def test_day_changes_at_midnight_in_japan(self):
        # 日本時間 10-09 23:30 と 10-10 00:30 は別の日（ページの決め方と同じ）
        before = datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc).timestamp()
        after = datetime(2026, 10, 9, 15, 30, tzinfo=timezone.utc).timestamp()
        self.assertNotEqual(today_index(2, before), today_index(2, after))

    def test_message_has_a_prefilled_post_link(self):
        text = message("ホームページの投稿", 0, 30)
        self.assertIn("https://x.com/intent/tweet?text=%E3%83%9B", text)
        self.assertIn("（1/30）", text)
        self.assertTrue(text.endswith("ホームページの投稿"))

    def test_sample_posts_come_with_their_image(self):
        post = "サンプルです（架空の店舗です）。\nhttps://sorasora1120.github.io/salon.html"
        self.assertTrue(image_for(post).endswith("/x-images/salon.jpg"))
        self.assertIn("x-images/salon.jpg", message(post, 2, 39))
        self.assertEqual(image_for("ホームページのコツ"), "")
        self.assertNotIn("付ける画像", message("ホームページのコツ", 0, 39))
