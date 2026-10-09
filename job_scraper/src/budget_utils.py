"""予算テキストから金額（円）を数値として取り出す共通ロジック。

CrowdWorks/ココナラとも「30,000円」のような直接表記が基本だが、ココナラの
一部の依頼では「5千円未満」「10万円〜」のような日本語の位取り略記が使われる。
`[\\d,]+\\s*円`だけでは"5"の直後が"千"のためマッチせず、無条件に「不明」扱いに
なって見積り要相談の候補に誤って混ざってしまう（2026-08-11発覚）。
"""
import re
import unicodedata

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


# 題名に書かれた金額（「【予算5万円固定】」「【税込1万円／…】」「【報酬5万】」）。
# 月額・時給・1本あたり・範囲（「5〜7万円」）は案件全体の金額ではないので読まない
_TITLE_PRICE_RE = re.compile(
    r"(?P<man>\d+(?:\.\d+)?)\s*万\s*円?|(?P<sen>\d+)\s*千\s*円|(?P<yen>\d{1,3}(?:,\d{3})+|\d{4,})\s*円"
)
_NOT_TOTAL_BEFORE_RE = re.compile(
    r"(?:月|月額|時給|時間|日給|単価|1\s*(?:本|ページ|枚|記事|投稿|件|商品|サイト|p|ヶ所|箇所|か所|文字|名|人)\s*(?:あたり)?)\s*[:：]?\s*$"
    r"|[〜~～\-－]\s*$"
)


def title_price_yen(title: str) -> int | None:
    """題名に書かれた案件全体の金額。1つだけはっきり書かれている時だけ返す（2026-10-09）。

    「【予算5万円固定】」の案件に予算欄の「500,005円」をそのまま見積りに出したり、「【税込1万円／…】」の
    案件に予算欄の範囲（1〜3万円）の真ん中の2万円を出したりしていた。依頼者が題名に書いた金額を
    超えて出すと、それだけで読まれなくなる。「万」は「円」が無くても「予算」「報酬」などの後なら読む。
    """
    t = unicodedata.normalize("NFKC", title or "")
    found = []
    for m in _TITLE_PRICE_RE.finditer(t):
        before, after = t[max(0, m.start() - 6):m.start()], t[m.end():m.end() + 2]
        if _NOT_TOTAL_BEFORE_RE.search(before) or re.match(r"\s*[〜~～\-－]\s*\d", after):
            continue
        if m.group("man") is not None:
            # 「10万PV」「5万人」のような数と区別するため、円が無い「万」は予算・報酬などの言葉の後だけにする
            if not m.group(0).rstrip().endswith("円") and not re.search(r"(?:予算|報酬|税込|総額|一式|固定)\D{0,2}$", before):
                continue
            found.append(int(float(m.group("man")) * 10000))
        elif m.group("sen") is not None:
            found.append(int(m.group("sen")) * 1000)
        else:
            found.append(int(m.group("yen").replace(",", "")))
    return found[0] if len(set(found)) == 1 else None


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

