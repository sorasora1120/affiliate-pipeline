"""締切テキストの正規化（相対表記を絶対日付に変換）。

スクレイピング時点の「あとN日」をそのままシートに保存すると、後から見たときに
「いつ時点のあとN日か」が分からず、時間が経つほど実態とズレて陳腐化する
（例: 3日前に検出した「あと2日」は、今日から見ればもう期限切れのはず）。
検出した瞬間の日付を基準にYYYY-MM-DD形式の絶対日付へ変換して保存することで、
ビューア側でいつ開いても正しい残り日数・期限切れ判定ができるようにする。
"""
import re
from datetime import date, timedelta

_RELATIVE_RE = re.compile(r"あと\s*(\d+)\s*日")
_ABSOLUTE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")


def normalize_deadline(raw_text: str, detected_date: date) -> str:
    """締切の生テキストをYYYY-MM-DD形式の絶対日付に正規化する。判定できなければ「不明」。"""
    if not raw_text:
        return "不明"
    m = _RELATIVE_RE.search(raw_text)
    if m:
        days = int(m.group(1))
        return (detected_date + timedelta(days=days)).strftime("%Y-%m-%d")
    m = _ABSOLUTE_RE.search(raw_text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return "不明"
    return "不明"
