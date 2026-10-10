"""成果の集計（1日1回、daily_stats.yml から実行）。

2026-10-08追加。200件応募して返信3件だったため、どんな案件に返信が来やすいかを数字で見て
改善を続けられるようにする。

- ユーザーには Discord に短いまとめを送る（今日の新着・送れる案件・応募→返信→採用の数）
- Claude の定期チェックは GitHub の注釈（::notice）から数字を読む（ログ本文は読めないため）

シートはビューアと同じ公開の gviz から、使う行・列だけ読む（サービスアカウントは使わない）。
進捗（応募済み・返信あり など）はビューアのボタンで付いた R列（進捗ステージ）を数えるので、
ボタンを押していない応募は数に入らない。
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
from src.budget_utils import parse_budget_yen  # noqa: E402
from src.worker_matcher import excluded_hit, has_weak_web_word, is_relevant_title, job_type  # noqa: E402

SHEET_ID = os.getenv("GOOGLE_SHEET_ID") or "1i2BtQulkchFt2dXxt9o6qLhdC7CXlBpv91EziyCp3o0"
SHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME") or "案件一覧"
JST = timezone(timedelta(hours=9))

# 2026-10-10、応募するアカウントを親の名義に書き換え、提案文の見積り（題名の金額を超えない）や最低予算（1万円）も
# 変えた。それより前の応募79件と分けて、変えてからの返信率を見る。応募した日はシートに無いので、
# この日以降に集めた案件への応募を「10-10以降の分」とみなす（前日に集めた案件へ応募した分は漏れる）
NEW_ACCOUNT_SINCE = "2026-10-10"

APPLIED = {"applied", "replied", "hired", "ordered", "rejected"}
REPLIED = {"replied", "hired", "ordered"}
HIRED = {"hired", "ordered"}
TYPE_JA = {
    "ec": "ネットショップ", "lp": "LP", "nocode": "STUDIO等", "recruit": "採用サイト",
    "renewal": "リニューアル・修正", "shop": "お店", "corporate": "会社", "wordpress": "WordPress",
    "default": "その他",
}


def fetch_rows(tq: str = "select A,C,E,Q,R,S where A = '提案済み' or R != ''") -> list[dict]:
    """既定では、提案済みの行と、進捗ステージが付いた行だけを読む。"""
    query = urllib.parse.urlencode({"tqx": "out:json", "sheet": SHEET_NAME, "tq": tq})
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    data = json.loads(text[text.index("(") + 1:text.rindex(")")])
    if data.get("status") == "error":
        raise RuntimeError(f"gvizの読み込みに失敗: {data.get('errors')}")

    def val(c):
        if c is None:
            return ""
        if c.get("f") is not None:
            return str(c["f"])
        return "" if c.get("v") is None else str(c["v"])

    keys = ["status", "title", "budget", "date", "stage", "applicants"]
    rows = []
    for r in data["table"]["rows"]:
        cells = [val(c) for c in (r.get("c") or [])]
        cells += [""] * (len(keys) - len(cells))
        rows.append(dict(zip(keys, cells)))
    return rows


def budget_band(text: str) -> str:
    amount = parse_budget_yen(text)
    if amount is None:
        return "見積り希望"
    if amount < 10000:
        return "1万円未満"
    if amount < 30000:
        return "1〜3万円"
    if amount < 100000:
        return "3〜10万円"
    return "10万円以上"


def applicants_band(text: str) -> str:
    try:
        n = int(float(text))
    except ValueError:
        return "不明"
    if n <= 5:
        return "5人以下"
    if n <= 15:
        return "6〜15人"
    return "16人以上"


def summarize(rows: list[dict], today: str) -> dict:
    s = {"pool": 0, "new_today": 0, "applied": 0, "replied": 0, "hired": 0, "pool_titles": [],
         "new_account": [0, 0, 0],  # 10-10以降の分（応募・返信・採用）
         "by_type": defaultdict(lambda: [0, 0]), "by_budget": defaultdict(lambda: [0, 0]),
         "by_applicants": defaultdict(lambda: [0, 0])}
    for r in rows:
        stage = r["stage"].strip()
        if r["status"] == "提案済み" and stage in ("", "new"):
            s["pool"] += 1
            s["pool_titles"].append(r["title"])
            if r["date"].startswith(today):
                s["new_today"] += 1
        if stage not in APPLIED:
            continue
        got_reply = stage in REPLIED
        s["applied"] += 1
        s["replied"] += got_reply
        s["hired"] += stage in HIRED
        if r["date"] >= NEW_ACCOUNT_SINCE:
            for i, hit in enumerate((True, got_reply, stage in HIRED)):
                s["new_account"][i] += hit
        for key, group in (("by_type", TYPE_JA[job_type(r["title"])]),
                           ("by_budget", budget_band(r["budget"])),
                           ("by_applicants", applicants_band(r["applicants"]))):
            s[key][group][0] += 1
            s[key][group][1] += got_reply
    return s


def rate(replied: int, applied: int) -> str:
    return f"{replied}/{applied}（{replied / applied * 100:.0f}%）" if applied else "0/0"


def breakdown(groups: dict) -> str:
    items = sorted(groups.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))
    return " / ".join(f"{name} {rate(r, a)}" for name, (a, r) in items) or "まだなし"


def discord_message(s: dict, today: str) -> str:
    lines = [
        f"📊 今日のまとめ（{today}）",
        f"送れる案件：{s['pool']}件（今日の新着 {s['new_today']}件）",
        f"応募 {s['applied']}件 → 返信 {s['replied']}件（{rate(s['replied'], s['applied'])}）→ 採用 {s['hired']}件",
        "うち{}以降の案件（親の名義・新しい提案文）：応募 {}件 → 返信 {}件 → 採用 {}件".format(NEW_ACCOUNT_SINCE[5:], *s["new_account"]),
    ]
    if s["replied"]:
        best = sorted(((n, a, r) for n, (a, r) in s["by_type"].items() if r), key=lambda x: (-x[2] / x[1], -x[2]))[:2]
        lines.append("返信が来やすい種類：" + "、".join(f"{n}（{rate(r, a)}）" for n, a, r in best))
    lines.append("※ 応募したら「① コピーして応募済みにする」、返信が来たら「💬 返信が来た」を押すと正確になります")
    return "\n".join(lines)


# フィルタで外れた案件の外れ方（注釈に出す順）
NEAR_MISS = "制作の言葉があるのに除外語に当たった"
DROP_KINDS = (NEAR_MISS, "予算未達", "要注意", "制作の言葉が無い")


def recent_outcomes(rows: list[dict], excluded_keywords: list[str]) -> tuple[str, dict[str, list[str]]]:
    """直近に集めた案件が、どのステータスになったかの内訳と、フィルタで外れた案件（外れ方ごと・新しい順）。

    2026-10-09追加。朝の収集で送れる案件が1件も増えなかったため、新着が本当に少ないのか、
    フィルタ（除外語・関連判定・要注意）で外しすぎているのかを、定期チェックで見分けられるようにする。
    2026-10-10、外れ方ごとに分けた。1つの一覧だと、除外語に当たった明らかに無関係な案件（eBayのリサーチ・
    アンケートなど、約400件）で埋まり、良い案件を落としていそうな「制作の言葉があるのに除外語に当たった」
    案件や予算未達の案件が見えなかったため。除外語に当たり制作の言葉も無い案件は出さない。
    """
    counts: dict[str, int] = defaultdict(int)
    dropped: dict[str, list[str]] = defaultdict(list)
    for r in reversed(rows):  # シートは下ほど新しい
        status, title = r["status"], r["title"]
        counts[status or "（空）"] += 1
        if status == "対象外（除外キーワード）":
            hit, relevant = excluded_hit(title, excluded_keywords), is_relevant_title(title)
            if hit and relevant:
                dropped[NEAR_MISS].append(f"{title} ←「{hit}」")
            elif not hit and not relevant:
                dropped["制作の言葉が無い"].append(title)
        elif status == "対象外（予算未達）":
            dropped["予算未達"].append(f"{title}（{r['budget'] or '予算なし'}）")
        elif status == "対象外（要注意）":
            dropped["要注意"].append(title)
    # 「サイト」「Web」はあるのに作業の言葉が無くて落ちた案件を先に出す（取りこぼしがあるならここ。2026-10-10）。
    # 何も無いもの（Instagram投稿・アンケートなど）は後ろ。並べ替えは安定なので、それぞれの中では新しい順のまま
    dropped["制作の言葉が無い"].sort(key=lambda t: not has_weak_web_word(t))
    summary = " / ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    return summary or "なし", dropped


def fit_annotation(items: list[str], limit_bytes: int = 4000) -> str:
    """注釈の本文は4096バイトで切れる（2026-10-10実測）ので、入るだけ並べて残りは件数で書く。"""
    out: list[str] = []
    for i, item in enumerate(items):
        after = len(items) - i - 1  # この項目のあとに残る件数
        tail = f" / ほか{after}件" if after else ""
        if len(" / ".join(out + [item]).encode()) + len(tail.encode()) > limit_bytes:
            return " / ".join(out + [f"ほか{len(items) - i}件"])
        out.append(item)
    return " / ".join(out) or "なし"


def annotation_chunks(items: list[str], limit_bytes: int = 4000, max_chunks: int = 1) -> list[str]:
    """fit_annotation の、注釈を max_chunks 個まで使う版。入りきらない分は最後の注釈に件数で書く。"""
    chunks: list[str] = []
    rest = list(items)
    while rest and len(chunks) < max_chunks - 1:
        n = 1
        while n < len(rest) and len(" / ".join(rest[:n + 1]).encode()) <= limit_bytes:
            n += 1
        chunks.append(" / ".join(rest[:n]))
        rest = rest[n:]
    if rest or not chunks:
        chunks.append(fit_annotation(rest, limit_bytes))
    return chunks


def main() -> None:
    # GitHub の注釈は1ステップ10個まで（2026-10-10、11個目に出した「送れる案件のタイトル」が出なかった）。
    # 大事なものから出す。今は最大9個（全体・返信率・送れる案件・行き先・外れた案件4種、うち1種は2つまで）
    today = datetime.now(JST).strftime("%Y-%m-%d")
    since = (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
    s = summarize(fetch_rows(), today)
    a, rp, h = s["new_account"]
    print(f"::notice title=全体::送れる案件 {s['pool']}件・今日の新着 {s['new_today']}件・"
          f"応募 {s['applied']}・返信 {s['replied']}・採用 {s['hired']}・返信率 {rate(s['replied'], s['applied'])}"
          f"｜{NEW_ACCOUNT_SINCE}以降に集めた案件への応募（親の名義・新しい提案文）：応募 {a}・返信 {rp}・採用 {h}・"
          f"返信率 {rate(rp, a)}")
    print(f"::notice title=返信率（種類別｜予算別｜応募者数別）::{breakdown(s['by_type'])} ｜ "
          f"{breakdown(s['by_budget'])} ｜ {breakdown(s['by_applicants'])}")
    # 変な案件が混ざっていないか、Claudeの定期チェックで目で確かめるため
    print(f"::notice title=送れる案件のタイトル（新しい順）::{fit_annotation(list(reversed(s['pool_titles'])))}")
    summary, dropped = recent_outcomes(fetch_rows(f"select A,C,E,Q,R,S where Q >= '{since}'"),
                                       config.WORKER_MATCH_EXCLUDE_KEYWORDS)
    print(f"::notice title={since}以降に集めた案件の行き先::{summary}")
    for kind in DROP_KINDS:
        items = list(dict.fromkeys(dropped.get(kind, [])))  # 同じ募集が何度も出るので1つにまとめる
        chunks = annotation_chunks(items, max_chunks=2 if kind == NEAR_MISS else 1)
        note = ""
        if kind == "制作の言葉が無い":
            note = f"・サイト/Webの言葉がある{sum(map(has_weak_web_word, items))}件が先"
        for i, chunk in enumerate(chunks, 1):
            part = f"・{i}/{len(chunks)}" if len(chunks) > 1 else ""
            print(f"::notice title=外れた案件：{kind}（{since}以降・{len(items)}件{note}・新しい順{part}）::{chunk}")
    if os.getenv("SEND_DISCORD") == "1":
        from src.notifier import notify_discord
        notify_discord(discord_message(s, today))


if __name__ == "__main__":
    main()
