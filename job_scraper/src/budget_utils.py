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
    man = _MAN_RE.search(text)
    if man:
        return int(man.group(1).replace(",", "")) * 10000
    sen = _SEN_RE.search(text)
    if sen:
        return int(sen.group(1).replace(",", "")) * 1000
    return None
