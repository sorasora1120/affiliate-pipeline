"""シートから題名の一部で案件をさがし、GitHub の注釈に出す（2026-10-10追加）。

返信が来た案件の中身（予算・募集文・URL・進み具合）を、Claude が相談のときに確かめるため
（ユーザーが送ってくる画面には題名の頭しか写らないことが多い）。シートは読むだけで書き換えない。
find_job.yml（手動）から、query に題名の一部を入れて動かす。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daily_stats import fetch_rows  # noqa: E402

KEYS = ["status", "title", "budget", "url", "date", "stage", "applicants", "description"]


def clean(text: str, limit: int) -> str:
    """注釈の本文に入れられる形にする（% と改行はそのままだと崩れる）。注釈は4096バイトで切れるので短くする。"""
    return text.replace("%", "%25").replace("\r", "").replace("\n", " ")[:limit]


def main() -> None:
    query = (os.getenv("QUERY") or "").replace("'", "").strip()
    if not query:
        sys.exit("query（題名の一部）を入れてください")
    rows = fetch_rows(f"select A,C,E,G,Q,R,S,T where C contains '{query}'", keys=KEYS)
    print(f"::notice title=見つかった件数::{len(rows)}件（{clean(query, 50)}）")
    # 注釈は1ステップ10個まで。新しい8件だけ出す
    for r in rows[-8:]:
        print(f"::notice title={r['status']} {r['date']} 段階 {r['stage'] or 'なし'} 応募者 {r['applicants'] or '?'}人::"
              f"{clean(r['title'], 150)} ｜ {clean(r['budget'], 40)} ｜ {r['url']} ｜ {clean(r['description'], 1000)}")


if __name__ == "__main__":
    main()
