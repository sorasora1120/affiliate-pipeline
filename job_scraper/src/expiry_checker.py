"""案件URLを実際に開いて、募集終了・契約済みになっていないか確認する。

提案済みとしてワーカーへ提示した案件でも、収集した時点から実際にクライアントへ
応募するまでの間に他の応募者へ決まってしまうことが多い（2026-08-11、提案済み
358件を全件ライブチェックしたところ220件＝61.5%が既に募集終了していた）。放置
すると Dispatch ビューアの「送れる案件」に閉じた案件が延々と溜まり、ユーザーが
実際に応募しようとして初めて気づく事態になる。

さらに2026-08-12、「古いやつ消して全部新しい物件にしろ」という指示を受け、
検出から日数が経った提案済み案件（まだ募集終了と確認できていなくても、古いほど
閉じているリスクが高い）を自動で鮮度切れ扱いにする仕組みも追加した
（find_stale_rows）。最初はユーザーの指示で手動一括処理したが、同じ状況が
繰り返し起こることが分かったため、find_closed_rowsの定期実行に組み込んで
自動化した。
"""
import logging
import re
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

from .deadline_utils import normalize_deadline

logger = logging.getLogger(__name__)

# 検索結果一覧のテキストからは締切を取得できない案件が多い（CrowdWorksは
# 「あとN日」表記が一覧側に出ないケースが大半、ココナラは一覧に締切情報自体が
# 載っていない）。ここで開く詳細ページには載っていることが多いため、募集終了
# チェックのついでに正確な締切も取り直す（2026-08-14、「全部に残り日数を書いて」
# との要望を受けて追加）。
#
# 2026-08-15、ページ全体を無差別に正規表現検索していたため、実際の締切
# （CrowdWorks「応募期限」欄=「2026年08月20日」のような漢字区切り。旧正規表現は
# スラッシュ/ハイフン区切りしか対応しておらず全く一致しなかった）ではなく、
# ページ内の無関係な日付（「掲載日」欄や、他の応募者のコメント投稿日時
# 「2026/08/13 21:20」等）を誤って締切として拾ってしまうバグが発覚した
# （提案済み166件中156件に「既に過ぎた締切」が入っていた）。ラベル文字列
# （CrowdWorks「応募期限」/ココナラ「募集期限」）が最初に出現する位置の直後
# だけを検索対象にすることで、無関係な日付を除外する。
_DEADLINE_RE = re.compile(r"あと\s*\d+\s*日|\d{4}[/\-年]\d{1,2}[/\-月]\d{1,2}日?")
_CW_DEADLINE_LABEL = "応募期限"
_CO_DEADLINE_LABEL = "募集期限"
_DEADLINE_SEARCH_WINDOW = 60  # ラベル直後、この文字数以内だけを見る

CLOSED_STATUS = "対象外（募集終了）"
STALE_STATUS = "対象外（鮮度切れ）"

# 2026-08-12、ユーザーの実測（3日より古い提案済みを手動除外）に合わせた閾値。
# 古い案件ほど実際には既に決まっている可能性が高いため、ライブチェックで
# 「募集終了」と確定できていなくても、鮮度だけで先に足切りする。
FRESHNESS_DAYS = 3

CW_CLOSED_MARKERS = ["このお仕事の募集は終了しています", "募集は終了", "契約済み"]
# 2026-08-15追加: 「募集期限」欄の要約行が「募集終了 締切日 2026年7月17日 / ...」の
# ように、他の文言と違って助詞なしの「募集終了」単体で出ることがあり、既存の
# マーカーではどれにも一致せず見逃していた（締切抽出自体は正しく動いていたのに、
# 実際は終了済みの案件が「開いている」と誤判定され続けていた）。
CO_CLOSED_MARKERS = ["この依頼は募集を終了しています", "募集を終了", "受付を終了", "募集終了"]


def find_stale_rows(rows: list[dict], platforms: set[str], today: date | None = None) -> list[int]:
    """検出日から`FRESHNESS_DAYS`日以上経過した「提案済み」行番号を返す（鮮度切れ）。"""
    today = today or date.today()
    cutoff = (today - timedelta(days=FRESHNESS_DAYS)).strftime("%Y-%m-%d")
    stale_rows: list[int] = []
    for i, r in enumerate(rows, start=2):
        if r.get("ステータス") != "提案済み":
            continue
        platform_key = "crowdworks" if r.get("プラットフォーム") == "CrowdWorks" else "coconala"
        if platform_key not in platforms:
            continue
        detected = r.get("検出日", "")
        if detected and detected < cutoff:
            stale_rows.append(i)
    return stale_rows


def find_closed_rows(url_rows: list[tuple[int, str]]) -> tuple[list[int], dict[int, str]]:
    """[(行番号, URL), ...] を受け取り、(募集終了と判定した行番号のリスト, {行番号: 締切}) を返す。

    締切は、詳細ページを開いたその日を基準に絶対日付へ正規化して返す
    （収集時点ではなく、いま開いて分かった残り日数のため）。既に募集終了と
    判定した行は締切を取り直す意味がないので対象に含めない。
    """
    closed_rows: list[int] = []
    deadlines: dict[int, str] = {}
    today = date.today()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
        ).new_page()
        try:
            for row_number, url in url_rows:
                if not url:
                    continue
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(1_200)
                    body_text = page.locator("body").inner_text()
                except Exception as exc:
                    logger.warning("募集終了チェックに失敗しました (%s): %s", url, exc)
                    continue
                markers = CW_CLOSED_MARKERS if "crowdworks.jp" in url else CO_CLOSED_MARKERS
                if any(m in body_text for m in markers):
                    closed_rows.append(row_number)
                    continue
                label = _CW_DEADLINE_LABEL if "crowdworks.jp" in url else _CO_DEADLINE_LABEL
                label_pos = body_text.find(label)
                if label_pos != -1:
                    window = body_text[label_pos : label_pos + len(label) + _DEADLINE_SEARCH_WINDOW]
                    deadline_match = _DEADLINE_RE.search(window)
                    if deadline_match:
                        normalized = normalize_deadline(deadline_match.group(0), today)
                        if normalized != "不明":
                            deadlines[row_number] = normalized
        finally:
            browser.close()
    return closed_rows, deadlines
