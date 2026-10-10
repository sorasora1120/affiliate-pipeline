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
        self.assertIn("インスタ", ideas[0])
        self.assertIn("LINE", ideas[1])

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


class TitlePriceTest(unittest.TestCase):
    # 2026-10-09、題名に「予算5万円固定」とあるのに予算欄の「500,005円」を、「税込1万円」とあるのに2万円を出していた
    def test_reads_only_a_single_total_price(self):
        from src.budget_utils import title_price_yen
        self.assertEqual(title_price_yen("【予算5万円固定】2店舗対応のシンプルなホームページ（LP）作成"), 50000)
        self.assertEqual(title_price_yen("【税込1万円／モック・素材あり】LPファーストビューのデザイン調整"), 10000)
        self.assertEqual(title_price_yen("【報酬5万】サイトの再構築と編集"), 50000)
        self.assertIsNone(title_price_yen("【継続・月5〜7万円見込み】LP・HP改善"))
        self.assertIsNone(title_price_yen("Kickstarterプロジェクトページのデザイン（1本30,000円〜）"))
        self.assertIsNone(title_price_yen("【時給3,000円〜】LPデザイン制作"))
        self.assertIsNone(title_price_yen("月間10万PVのメディアのWordPress改修"))
        self.assertIsNone(title_price_yen("2026年10月公開のLP制作"))

    def test_quote_never_exceeds_the_title_price(self):
        rows = [_row(タイトル="【予算5万円固定】シンプルなホームページ（LP）作成", 予算="500,005円"),
                _row(タイトル="【税込1万円／モック・素材あり】LPファーストビューのデザイン調整", 予算="10,000円 〜 30,000円"),
                _row(タイトル="【予算3万円】ホームページ制作", 予算="契約金額はワーカーと相談する")]
        cands, below, _ = find_candidates(rows, CATEGORIES, EXCLUDE, 5000, 20, 1000, 30000)
        self.assertEqual(below, [])
        self.assertEqual([c["amount"] for c in cands], [50000, 10000, 30000])

    def test_title_price_below_minimum_is_below_budget(self):
        cands, below, _ = find_candidates([_row(タイトル="【3,000円】LPの修正", 予算="〜 5,000円")],
                                          CATEGORIES, EXCLUDE, 5000, 20, 1000, 30000)
        self.assertEqual(cands, [])
        self.assertEqual(below, [2])


class ReviewProposedBelowBudgetTest(unittest.TestCase):
    # 2026-10-09、最低予算を1万円に上げた時、まだ手を付けていない小さい案件を「送れる案件」から外す
    def test_untouched_small_jobs_are_moved_out(self):
        from src.worker_matcher import review_proposed_rows
        rows = [_row(ステータス="提案済み", 進捗ステージ="", 予算="5,000円"),
                _row(ステータス="提案済み", 進捗ステージ="", 予算="10,000円 〜 30,000円"),
                _row(ステータス="提案済み", 進捗ステージ="applied", 予算="5,000円"),
                _row(ステータス="提案済み", 進捗ステージ="", タイトル="【税込8,000円】LPの修正", 予算="10,000円 〜 30,000円")]
        irrelevant, below, refreshed = review_proposed_rows(rows, EXCLUDE, 10000, 20, 1000, 30000)
        self.assertEqual(irrelevant, [])
        self.assertEqual(below, [2, 5])
        self.assertEqual([c["row"] for c in refreshed], [3])


class RoughLineTest(unittest.TestCase):
    def test_matches_the_size_of_the_job(self):
        from src.worker_matcher import _rough_line
        self.assertIn("ファーストビュー", _rough_line("看護師向けLPのファーストビュー1画面デザイン"))
        self.assertIn("作業の範囲", _rough_line("WordPressのレイアウト修正"))
        self.assertIn("LPの構成図", _rough_line("美容サロンのLP制作"))
        self.assertIn("トップページの構成図", _rough_line("コーポレートサイトのリニューアル"))


class RelevantTitleWeakWordTest(unittest.TestCase):
    def test_site_only_titles_need_a_work_word(self):
        from src.worker_matcher import is_relevant_title
        self.assertFalse(is_relevant_title("SNS版ポータルサイトに出演してくださる女性の方を募集します。"))
        self.assertFalse(is_relevant_title("サイト運営スタッフ募集"))
        self.assertTrue(is_relevant_title("ポータルサイト制作"))
        self.assertTrue(is_relevant_title("ECサイトの構築をお願いします"))
        self.assertTrue(is_relevant_title("Webデザインのご依頼"))

    def test_strong_words_pass_alone(self):
        from src.worker_matcher import is_relevant_title
        self.assertTrue(is_relevant_title("ホームページをお願いします"))
        self.assertTrue(is_relevant_title("LP1枚"))
        self.assertTrue(is_relevant_title("Shopifyのお手伝い"))

    def test_netshop_needs_a_work_word(self):
        from src.worker_matcher import is_relevant_title
        self.assertFalse(is_relevant_title("ネットショップ集客"))
        self.assertTrue(is_relevant_title("ネットショップを作りたいです"))
        self.assertTrue(is_relevant_title("ネットショップ開設のお手伝い"))

    def test_page_work_and_wordpress_spellings(self):
        # 2026-10-09、外した案件を見直して見つけた取りこぼし
        from src.worker_matcher import is_relevant_title
        self.assertTrue(is_relevant_title("会話教室のトップページの作成依頼"))
        self.assertTrue(is_relevant_title("TOPページのテキスト流し込み・画像差し替え・配置"))
        self.assertTrue(is_relevant_title("新規事業(MEO対策事業)のサービスページを作成して欲しい"))
        self.assertTrue(is_relevant_title("Word Pressの修正ができる方"))
        self.assertTrue(is_relevant_title("WordPresssの投稿画面・遅延改善作業"))
        self.assertTrue(is_relevant_title("WPのコンタクトフォーム"))
        # 画像やSNSの仕事は今までどおり落とす
        self.assertFalse(is_relevant_title("ふるさと納税 返礼品ページの商品画像デザイン制作"))
        self.assertFalse(is_relevant_title("【20代歓迎◎】国内旅行が好きな方へ｜Instagram投稿デザイン制作"))
        self.assertFalse(is_relevant_title("Amazon商品画像（9枚）の修正・リニューアル"))


class TitleExcludedTest(unittest.TestCase):
    def test_ascii_keywords_match_whole_words_only(self):
        from src.worker_matcher import title_has_excluded
        kws = ["CFO", "BASE", "楽天"]
        self.assertFalse(title_has_excluded("自社ECサイト（ECFORCE使用）のLPコーディング担当者募集", kws))
        self.assertFalse(title_has_excluded("DATABASE連携のサイト制作", kws))
        self.assertTrue(title_has_excluded("CFO候補募集", kws))
        self.assertTrue(title_has_excluded("BASEでネットショップ開設", kws))
        self.assertTrue(title_has_excluded("楽天の商品ページ作成", kws))

    def test_real_web_jobs_are_not_excluded(self):
        import config
        from src.worker_matcher import is_relevant_title, title_has_excluded
        for title in ["配信者・ライバー向けのウェブメディア・WebサービスのTOPページデザイン",
                      "【経験者歓迎】　自社ECサイト（ECFORCE使用）のLPコーディング担当者募集",
                      "メルマガ登録フォーム付きのLP制作",
                      # 2026-10-10、バナー・画像加工・記事LPに当たって落としていた
                      "TOPページの原稿差し替えおよび画像加工＆コーディング",
                      "記事LPのコーディングをお願いしたい。",
                      "【セルフネイルブランド✨】LPデザイン＆広告バナー制作のお仕事"]:
            self.assertTrue(is_relevant_title(title) and not title_has_excluded(title, config.WORKER_MATCH_EXCLUDE_KEYWORDS), title)

    def test_soft_keywords_still_exclude_unless_the_work_is_clear(self):
        import config
        from src.worker_matcher import excluded_hit
        kws = config.WORKER_MATCH_EXCLUDE_KEYWORDS
        # バナーだけ・文章を書く記事LP・「LP・バナー制作」のデザイナー募集は外れたまま
        for title, hit in [("【継続依頼あり◎】暮らし・ひとり時間をテーマにしたWebバナー制作", "バナー"),
                           ("D2Cブランド_記事LPの作成依頼", "記事LP"),
                           ("【継続あり】場所や時間に縛られない働き方を目指すWebデザイナー募集｜LP・バナー制作", "バナー"),
                           ("ECサイトの商品画像の画像加工", "画像加工"),
                           # ほかの除外語にも当たれば、そちらの語で外れる
                           ("LPデザイン・バナー制作｜時給1,500円〜", "時給"),
                           ("【完全在宅】EC・広告クリエイティブ経験者歓迎✨LPデザイン・バナー制作", "広告クリエイティブ")]:
            self.assertEqual(excluded_hit(title, kws), hit, title)


class RecheckExcludedTest(unittest.TestCase):
    def test_recent_wrongly_excluded_rows_come_back(self):
        from datetime import date
        from src.worker_matcher import EXCLUDED_KEYWORD_STATUS
        today = date.today().strftime("%Y-%m-%d")
        rows = [
            _row(ステータス=EXCLUDED_KEYWORD_STATUS, タイトル="ECFORCEのLPコーディング", 検出日=today),
            _row(ステータス=EXCLUDED_KEYWORD_STATUS, タイトル="ECFORCEのLPコーディング", 検出日="2020-01-01"),
            _row(ステータス=EXCLUDED_KEYWORD_STATUS, タイトル="動画の編集", 検出日=today),
        ]
        cands, below, excluded = find_candidates(rows, CATEGORIES, ["CFO", "動画"], 5000, 20, 1000, 30000)
        self.assertEqual([c["row"] for c in cands], [2])
        self.assertEqual(excluded, [])


class JobCategoriesConfigTest(unittest.TestCase):
    def test_category_labels_are_matching_targets(self):
        import config
        self.assertTrue(config.JOB_CATEGORIES)
        for label, cid in config.JOB_CATEGORIES:
            self.assertIn(label, config.WORKER_MATCH_CATEGORIES, label)
            self.assertTrue(cid.isdigit(), cid)

