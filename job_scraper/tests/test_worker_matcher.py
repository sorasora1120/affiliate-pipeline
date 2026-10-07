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
