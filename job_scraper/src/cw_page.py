"""CrowdWorksの案件ページ本文（inner_text）から情報を取り出す共通処理。

案件収集時の依頼者情報取得（detail_fetcher.py）と、募集終了チェック
（expiry_checker.py）の両方が同じページを開くため、ここにまとめる。
"""
import re

# 「応募状況」欄の「応募した人 12 人」
_APPLICANTS_RE = re.compile(r"応募した人\s*(\d+)\s*人")

# 募集文（「仕事の詳細」見出しの直後から、次の欄の見出しまで）
_DESCRIPTION_LABEL = "仕事の詳細"
_DESCRIPTION_END_LABELS = ["応募状況", "クライアント情報", "この仕事に応募", "気になるリストに追加"]
DESCRIPTION_MAX_CHARS = 1500


def parse_applicants(body_text: str) -> str:
    m = _APPLICANTS_RE.search(body_text)
    return m.group(1) if m else ""


def parse_description(body_text: str) -> str:
    start = body_text.find(_DESCRIPTION_LABEL)
    if start == -1:
        return ""
    text = body_text[start + len(_DESCRIPTION_LABEL):]
    ends = [i for i in (text.find(label) for label in _DESCRIPTION_END_LABELS) if i > 0]
    if ends:
        text = text[:min(ends)]
    return text.strip()[:DESCRIPTION_MAX_CHARS]
