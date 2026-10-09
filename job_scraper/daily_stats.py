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

from src.budget_utils import parse_budget_yen  # noqa: E402
from src.worker_matcher import job_type  # noqa: E402

SHEET_ID = os.getenv("GOOGLE_SHEET_ID") or "1i2BtQulkchFt2dXxt9o6qLhdC7CXlBpv91EziyCp3o0"
SHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME") or "案件一覧"
JST = timezone(timedelta(hours=9))

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
    ]
    if s["replied"]:
        best = sorted(((n, a, r) for n, (a, r) in s["by_type"].items() if r), key=lambda x: (-x[2] / x[1], -x[2]))[:2]
        lines.append("返信が来やすい種類：" + "、".join(f"{n}（{rate(r, a)}）" for n, a, r in best))
    lines.append("※ 応募したら「① コピーして応募済みにする」、返信が来たら「💬 返信が来た」を押すと正確になります")
    return "\n".join(lines)


def recent_outcomes(rows: list[dict]) -> tuple[str, list[str]]:
    """直近に集めた案件が、どのステータスになったかの内訳と、フィルタで外れた案件のタイトル。

    2026-10-09追加。朝の収集で送れる案件が1件も増えなかったため、新着が本当に少ないのか、
    フィルタ（除外語・関連判定・要注意）で外しすぎているのかを、定期チェックで見分けられるようにする。
    """
    counts: dict[str, int] = defaultdict(int)
    dropped = []
    for r in rows:
        counts[r["status"] or "（空）"] += 1
        if r["status"] in ("対象外（除外キーワード）", "対象外（要注意）"):
            dropped.append(f"[{r['status'][4:-1]}] {r['title']}")
    summary = " / ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    return summary or "なし", dropped


def main() -> None:
    today = datetime.now(JST).strftime("%Y-%m-%d")
    since = (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
    recent = fetch_rows(f"select A,C,E,Q,R,S where Q >= '{since}'")
    summary, dropped = recent_outcomes(recent)
    print(f"::notice title={since}以降に集めた案件の行き先::{summary}")
    print(f"::notice title=フィルタで外れた案件（{since}以降・最大50件）::{' / '.join(dropped[-50:]) or 'なし'}")
    s = summarize(fetch_rows(), today)
    print(f"::notice title=全体::送れる案件 {s['pool']}件・今日の新着 {s['new_today']}件・"
          f"応募 {s['applied']}・返信 {s['replied']}・採用 {s['hired']}・返信率 {rate(s['replied'], s['applied'])}")
    print(f"::notice title=種類別の返信率::{breakdown(s['by_type'])}")
    print(f"::notice title=予算別の返信率::{breakdown(s['by_budget'])}")
    print(f"::notice title=応募者数別の返信率::{breakdown(s['by_applicants'])}")
    # 変な案件が混ざっていないか、Claudeの定期チェックで目で確かめるため（新しい順に最大60件）
    print(f"::notice title=送れる案件のタイトル::{' / '.join(reversed(s['pool_titles'][-60:]))}")
    if os.getenv("SEND_DISCORD") == "1":
        from src.notifier import notify_discord
        notify_discord(discord_message(s, today))


if __name__ == "__main__":
    main()
