import unittest

from daily_stats import NEAR_MISS, annotation_chunks, discord_message, fit_annotation, recent_outcomes, summarize


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


class RecentOutcomesTest(unittest.TestCase):
    def test_splits_filtered_titles_by_how_they_were_dropped(self):
        ex = "対象外（除外キーワード）"
        rows = [_r(), _r(status=ex, title="WEBデザイン講師募集"), _r(status=ex, title="セミナー集客のLP制作"),
                _r(status=ex, title="アンケート回答のお願い"), _r(status=ex, title="ブログの文章作成"),
                _r(status="対象外（予算未達）", title="安い案件", budget="5,000円"),
                _r(status="対象外（要注意）", title="成果報酬のLP")]
        summary, dropped = recent_outcomes(rows, ["講師募集", "セミナー", "アンケート回答", "成果報酬"])
        self.assertIn("提案済み 1", summary)
        self.assertIn("対象外（除外キーワード） 4", summary)
        # 新しい順（シートの下から）。除外語に当たり制作の言葉も無い「アンケート回答」は出さない
        self.assertEqual(dropped[NEAR_MISS], ["セミナー集客のLP制作 ←「セミナー」", "WEBデザイン講師募集 ←「講師募集」"])
        self.assertEqual(dropped["制作の言葉が無い"], ["ブログの文章作成"])
        self.assertEqual(dropped["予算未達"], ["安い案件（5,000円）"])
        self.assertEqual(dropped["要注意"], ["成果報酬のLP"])


class FitAnnotationTest(unittest.TestCase):
    def test_cuts_at_the_byte_limit_and_counts_the_rest(self):
        items = ["あ" * 10] * 5  # 1件30バイト
        self.assertEqual(fit_annotation(items, limit_bytes=1000), " / ".join(items))
        text = fit_annotation(items, limit_bytes=80)
        self.assertLessEqual(len(text.encode()), 80)
        self.assertEqual(text, " / ".join(["あ" * 10] * 2 + ["ほか3件"]))
        self.assertEqual(fit_annotation([]), "なし")

    def test_chunks_use_more_annotations_before_counting_the_rest(self):
        items = ["あ" * 10] * 5  # 1件30バイト、1つの注釈に2件（63バイト）まで
        self.assertEqual(annotation_chunks(items, limit_bytes=70, max_chunks=2),
                         [" / ".join(["あ" * 10] * 2), " / ".join(["あ" * 10] + ["ほか2件"])])
        self.assertEqual(annotation_chunks(items[:2], limit_bytes=70, max_chunks=2), [" / ".join(["あ" * 10] * 2)])
        self.assertEqual(annotation_chunks([], max_chunks=2), ["なし"])

