"""予算テキストから金額（円）を数値として取り出す共通ロジック。

CrowdWorks/ココナラとも「30,000円」のような直接表記が基本だが、ココナラの
一部の依頼では「5千円未満」「10万円〜」のような日本語の位取り略記が使われる。
`[\\d,]+\\s*円`だけでは"5"の直後が"千"のためマッチせず、無条件に「不明」扱いに
なって見積り要相談の候補に誤って混ざってしまう（2026-08-11発覚）。
"""
import re

_PLAIN_RE = re.compile(r"([\d,]+)\s*円")
_MAN_RE = re.compile(r"([\d,]+)\s*万\s*円")
_SEN_RE = re.compile(r"([\d,]+)\s*千\s*円")


def parse_budget_yen(text: str) -> int | None:
    """予算テキストから金額（円）を取り出す。範囲表記は上限を採用する。

    見つからなければNone（「見積り希望」等、本当に金額情報がないケース）。
    """
    if not text:
        return None
    plain = _PLAIN_RE.findall(text)
    if plain:
        # 「30,000円 〜 50,000円」のような範囲は最後（＝上限）を使う
        return int(plain[-1].replace(",", ""))
    # 「5万円 〜 10万円」の範囲も上限を使う（ランサーズで多い表記）
    man = _MAN_RE.findall(text)
    if man:
        return int(man[-1].replace(",", "")) * 10000
    sen = _SEN_RE.findall(text)
    if sen:
        return int(sen[-1].replace(",", "")) * 1000
    return None


def quote_budget_yen(text: str) -> int | None:
    """提案文で出す金額。範囲表記（「30,000円 〜 50,000円」）は真ん中を千円単位で切り捨てて使う。

    2026-10-08、200件応募して返信3件だったため。評価0件のうちに依頼者の上限ぴったりで出すと
    割高に見えるので、範囲の真ん中にする。範囲でなければ parse_budget_yen と同じ。
    """
    if not text:
        return None
    for regex, unit in ((_PLAIN_RE, 1), (_MAN_RE, 10000), (_SEN_RE, 1000)):
        found = [int(x.replace(",", "")) * unit for x in regex.findall(text)]
        if not found:
            continue
        low, high = found[0], found[-1]
        if len(found) < 2 or low >= high:
            return high
        return max(low, (low + high) // 2 // 1000 * 1000)
    return None

