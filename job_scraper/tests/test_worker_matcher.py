import unittest

from src.worker_matcher import find_candidates

CATEGORIES = {"サイト制作"}
EXCLUDE = ["動画", "イラスト"]


def _row(**overrides):
    row = {
        "カテゴリ": "サイト制作",
        "ステータス": "未チェック",
        "タイトル": "コーポレートサイト制作",
        "予算": "100000円",
        "URL": "https://example.com",
    }
    row.update(overrides)
    return row


def _match(rows):
    return find_candidates(
        rows,
        target_categories=CATEGORIES,
        excluded_keywords=EXCLUDE,
        min_budget_yen=40000,
        margin_percent=20,
        margin_min_yen=3000,
        margin_max_yen=30000,
    )


def test_matching_row_becomes_candidate():
    candidates, below_budget, excluded = _match([_row()])
    assert len(candidates) == 1
    assert below_budget == []
    assert excluded == []


def test_excluded_keyword_title_is_reported_not_silently_dropped():
    rows = [_row(タイトル="動画制作のご依頼")]
    candidates, below_budget, excluded = _match(rows)
    assert candidates == []
    assert below_budget == []
    assert excluded == [2]


def test_below_budget_row_is_reported():
    rows = [_row(予算="10000円")]
    candidates, below_budget, excluded = _match(rows)
    assert candidates == []
    assert below_budget == [2]
    assert excluded == []


def test_wrong_category_is_ignored_entirely():
    rows = [_row(カテゴリ="ロゴ")]
    candidates, below_budget, excluded = _match(rows)
    assert candidates == below_budget == excluded == []


def test_already_processed_row_is_skipped():
    rows = [_row(ステータス="提案済み")]
    candidates, below_budget, excluded = _match(rows)
    assert candidates == below_budget == excluded == []


def test_profit_is_left_after_platform_fee():
    from src.worker_matcher import platform_fee, split_amount

    # CrowdWorks: 10万円以下20%、10万〜20万10%、20万超5%
    assert platform_fee("CrowdWorks", 50_000) == 10_000
    assert platform_fee("CrowdWorks", 300_000) == 20_000 + 10_000 + 5_000
    fee, margin, quote = split_amount("CrowdWorks", 50_000, 20, 3000, 30000)
    assert fee + margin + quote == 50_000
    assert margin == 10_000


def test_wish_sentence_is_picked_from_description():
    from src.worker_matcher import pick_wish_sentence

    desc = (
        "【概要】\n美容室のホームページ制作をお願いします。\n"
        "・ナチュラルで落ち着いた雰囲気にしたいです。\n"
        "・報酬は5万円を予定しています。\n"
        "・ご応募の際は実績をお送りください。\n"
    )
    assert pick_wish_sentence(desc) == "ナチュラルで落ち着いた雰囲気にしたいです"
    assert pick_wish_sentence("報酬は3万円です。ご応募お待ちしています。") == ""
    assert pick_wish_sentence("") == ""


def test_wish_sentence_skips_headings_and_self_intro():
    from src.worker_matcher import pick_wish_sentence

    assert pick_wish_sentence("【お願いしたい内容】\nお問い合わせページ\n") == ""
    assert pick_wish_sentence("当方は企業様の集客支援を行っている営業会社です。") == ""
    assert pick_wish_sentence("店舗用とEC用で残高が分断される構成は、目的を満たしません。") == ""
    desc = "【依頼の目的・背景】\n特にスマートフォンでの閲覧を重視した設計を希望します。\n"
    assert pick_wish_sentence(desc) == "特にスマートフォンでの閲覧を重視した設計を希望します"


class AdaptPlanTest(unittest.TestCase):
    def test_adds_pages_mentioned_in_description(self):
        from src.worker_matcher import adapt_plan
        plan = "トップ → 事業内容 → 会社概要 → お問い合わせ"
        out, added = adapt_plan(plan, "ブログとよくある質問のページも作ってください。施工事例も載せたいです。")
        self.assertEqual(added, ["お知らせ・ブログ", "よくある質問", "実績・事例"])
        self.assertTrue(out.endswith("→ お問い合わせ"))

    def test_ignores_conditions_for_applicants(self):
        from src.worker_matcher import adapt_plan
        plan = "トップ → 事業内容 → お問い合わせ"
        desc = "実績のある方を優先します。採用させていただいた方にはご連絡します。アクセス解析の知識があれば尚可。結果はお知らせください。"
        out, added = adapt_plan(plan, desc)
        self.assertEqual(added, [])
        self.assertEqual(out, plan)

    def test_skips_pages_already_in_plan(self):
        from src.worker_matcher import adapt_plan
        plan = "トップ → メニュー・料金 → アクセス → 予約ボタン（どこからでも押せる位置に）"
        out, added = adapt_plan(plan, "料金表とネット予約、地図を入れてください")
        self.assertEqual(added, [])


class PickIdeasTest(unittest.TestCase):
    def test_uses_description_specific_ideas_first(self):
        from src.worker_matcher import pick_ideas
        ideas = pick_ideas("shop", "インスタと連携して、LINEで予約を受けたいです")
        self.assertEqual(len(ideas), 3)
        self.assertIn("インスタ", ideas[0][0])
        self.assertIn("LINE", ideas[1][1])

    def test_ignores_line_inside_other_words_and_applicant_conditions(self):
        from src.worker_matcher import pick_ideas, _PITCH
        ideas = pick_ideas("corporate", "Online meeting OK. deadline is flexible. 海外在住の方も歓迎です")
        self.assertEqual(ideas, _PITCH["corporate"]["ideas"])


class RedFlagTest(unittest.TestCase):
    def test_flags_unpaid_and_off_platform(self):
        from src.worker_matcher import red_flag
        self.assertEqual(red_flag("報酬は成果報酬となります"), "報酬なし・成果報酬")
        self.assertEqual(red_flag("詳細はLINE交換のうえお伝えします"), "クラウドワークスの外でのやり取り")
        self.assertEqual(red_flag("初期費用として3万円が必要です"), "怪しい勧誘")

    def test_normal_job_is_not_flagged(self):
        from src.worker_matcher import red_flag
        self.assertEqual(red_flag("美容室のホームページを作りたいです。LINE予約のボタンも付けてください。"), "")


class RelevantTitleTest(unittest.TestCase):
    def test_coding_jobs_are_relevant(self):
        from src.worker_matcher import is_relevant_title
        self.assertTrue(is_relevant_title("HTML/CSSのコーディングをお願いします"))
        self.assertTrue(is_relevant_title("HTMLの修正依頼"))


class QuoteBudgetTest(unittest.TestCase):
    def test_range_uses_middle(self):
        from src.budget_utils import quote_budget_yen
        self.assertEqual(quote_budget_yen("30,000円 〜 50,000円"), 40000)
        self.assertEqual(quote_budget_yen("10,000円 〜 25,000円"), 17000)
        self.assertEqual(quote_budget_yen("5万円 〜 10万円"), 75000)

    def test_single_amount_is_unchanged(self):
        from src.budget_utils import quote_budget_yen
        self.assertEqual(quote_budget_yen("80,000円"), 80000)
        self.assertEqual(quote_budget_yen("〜 5,000円"), 5000)
        self.assertIsNone(quote_budget_yen("見積り希望"))

    def test_candidate_quotes_middle_but_eligibility_uses_upper(self):
        cands, below, _ = find_candidates([_row(予算="3,000円 〜 8,000円")], CATEGORIES, EXCLUDE, 5000, 20, 1000, 30000)
        self.assertEqual(below, [])
        self.assertEqual(cands[0]["amount"], 5000)
        cands, below, _ = find_candidates([_row(予算="1,000円 〜 4,000円")], CATEGORIES, EXCLUDE, 5000, 20, 1000, 30000)
        self.assertEqual(cands, [])

