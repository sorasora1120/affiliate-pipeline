import unittest

from daily_stats import discord_message, summarize


def _r(stage="", status="提案済み", title="美容室のホームページ制作", budget="50,000円", date="2026-10-08", applicants="3"):
    return {"status": status, "title": title, "budget": budget, "date": date, "stage": stage, "applicants": applicants}


class SummarizeTest(unittest.TestCase):
    def test_counts_pool_applied_replied_hired(self):
        rows = [_r(), _r(date="2026-10-07"), _r("applied"), _r("replied", title="LP制作"), _r("ordered", status="対象外（募集終了）"),
                _r("rejected")]
        s = summarize(rows, "2026-10-08")
        self.assertEqual((s["pool"], s["new_today"]), (2, 1))
        self.assertEqual((s["applied"], s["replied"], s["hired"]), (4, 2, 1))
        self.assertEqual(s["by_type"]["LP"], [1, 1])
        self.assertEqual(s["by_type"]["お店"], [3, 1])
        self.assertEqual(s["by_applicants"]["5人以下"], [4, 2])

    def test_message_mentions_best_type_only_when_replied(self):
        s = summarize([_r("applied")], "2026-10-08")
        self.assertNotIn("返信が来やすい", discord_message(s, "2026-10-08"))
        s = summarize([_r("replied", title="LP制作"), _r("applied")], "2026-10-08")
        self.assertIn("返信が来やすい種類：LP（1/1（100%））", discord_message(s, "2026-10-08"))
