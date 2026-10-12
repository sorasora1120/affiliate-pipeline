import unittest
from datetime import datetime, timezone

from x_daily_post import image_for, load_images, load_posts, message, today_index


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

    def test_images_come_from_the_shared_list(self):
        # 2026-10-12〜、x_posts.js の X_IMAGES（X_DAILY と同じ並び）で案ごとに画像を決める
        js = 'var X_DAILY = [\n  "一つ目",\n  "二つ目",\n];\nvar X_IMAGES = [\n  "x-images/a.jpg",\n  "",\n];\nfunction f() {}'
        self.assertEqual(load_posts(js), ["一つ目", "二つ目"])
        self.assertEqual(load_images(js), ["x-images/a.jpg", ""])
        self.assertTrue(image_for("一つ目", "x-images/a.jpg").endswith("/dispatch-viewer/main/x-images/a.jpg"))
        self.assertIn("x-images/a.jpg", message("一つ目", 0, 2, image_for("一つ目", "x-images/a.jpg")))
        self.assertNotIn("付ける画像", message("二つ目", 1, 2, image_for("二つ目", "")))
        self.assertEqual(load_images('var X_DAILY = [\n  "a",\n];'), [])

    def test_names_in_the_header_comment_are_ignored(self):
        # 先頭のコメントに「var X_IMAGES = [」と書いてあっても、本物の並びを読む
        js = ('// 「var X_DAILY = [」と「var X_IMAGES = [」から読む\nvar X_DAILY = [\n  "一つ目",\n];\n'
              'var X_IMAGES = [\n  "x-images/a.jpg",\n];\n')
        self.assertEqual(load_posts(js), ["一つ目"])
        self.assertEqual(load_images(js), ["x-images/a.jpg"])
