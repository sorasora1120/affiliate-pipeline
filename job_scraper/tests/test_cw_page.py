from src.cw_page import is_competition


# 2026-10-12 に CrowdWorks の一覧・詳細ページから写した文字（コンペ形式を外すため）
CARD_COMPETITION = ("新着 【3万円／短期募集】新規ブランド「MEGURU」ロゴデザイン｜資源を、香りで巡らせる。 ロゴ作成・ロゴデザイン "
                    "新規ブランド・プロジェクト「MEGURU」のロゴデザインを募集します。 ... コンペ 30,000 円 提案数 8件 あと 3 日 "
                    "（10月15日まで） Oneder 掲載日： 2026年10月12日 気になる")
# 募集文に「コンペ時は」とあるが、固定報酬の案件
CARD_FIXED_MENTIONS_COMPETITION = ("新着 布団収納袋パッケージデザイン制作 包装・パッケージデザイン 【 概要 】 新商品 布団収納袋のパッケージデザイン制作 "
                                   "・両面デザインですが、コンペ時は表面のみで問題ございません 【 契約金... 固定報酬制 33,000円 応募数 19 人 "
                                   "契約状況 0/1人 あと 9 日 （10月21日まで） THREESTEP")
DETAIL_COMPETITION = ("書籍の表紙デザイン案のお願い 仕事の概要 コンペ 1,100円 ※採用確約あり 掲載日 2026年10月11日 応募期限 2026年10月13日 "
                      "応募状況 提案した人 20 人気になる！リスト 31 人 この仕事の提案一覧を見る 仕事の詳細 ご覧いただきありがとうございます。")
DETAIL_FIXED = ("【SNSデザイン作成】便利グッズ・生活雑貨の紹介画像制作 仕事の概要 固定報酬制 30,000円 〜 50,000円 納品希望日 - "
                "応募状況 応募した人 4 人契約した人 0 人募集人数 5 人 仕事の詳細 暮らしに役立つ便利グッズや生活雑貨を紹介する")


def test_competition_card_and_detail():
    assert is_competition(CARD_COMPETITION) is True
    assert is_competition(DETAIL_COMPETITION) is True


def test_fixed_price_is_not_competition():
    assert is_competition(CARD_FIXED_MENTIONS_COMPETITION) is False
    assert is_competition(DETAIL_FIXED) is False
    assert is_competition("") is False
