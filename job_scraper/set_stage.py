"""シートの1行に「進捗ステージ」（R列）を付ける（2026-10-10追加）。

ユーザーがビューアのボタン（「💬 返信が来た」など）を押し忘れた進み具合を、相談で分かった時に Claude が付けるため
（初めての返信が来たのに、ビューアで付いておらず、成果のまとめの返信率が0%のままだった）。
URL が一致する行の「進捗ステージ」だけを書き換える。値はビューアのボタンと同じ。set_stage.yml（手動）から動かす。
"""
import json
import os
import sys

import gspread
from google.oauth2.service_account import Credentials

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.sheets_writer import HEADER, SCOPES  # noqa: E402

STAGES = {"applied", "replied", "hired", "ordered", "rejected"}


def same_job(a: str, b: str) -> bool:
    return a.split("?")[0].strip().rstrip("/") == b.split("?")[0].strip().rstrip("/")


def main() -> None:
    url, stage = (os.getenv("JOB_URL") or "").strip(), (os.getenv("STAGE") or "").strip()
    if stage not in STAGES or not url.startswith("https://crowdworks.jp/public/jobs/"):
        sys.exit(f"URL か stage が正しくありません: {url!r} {stage!r}")
    creds = Credentials.from_service_account_info(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]), scopes=SCOPES)
    ws = gspread.authorize(creds).open_by_key(os.environ["GOOGLE_SHEET_ID"]).worksheet(
        os.getenv("GOOGLE_WORKSHEET_NAME") or "案件一覧")
    url_col, stage_col = HEADER.index("URL") + 1, HEADER.index("進捗ステージ") + 1
    rows = [i for i, u in enumerate(ws.col_values(url_col), start=1) if i > 1 and same_job(u, url)]
    if not rows:
        sys.exit(f"シートに見つかりませんでした: {url}")
    for row in rows:
        before = ws.cell(row, stage_col).value or "空"
        ws.update_cell(row, stage_col, stage)
        print(f"::notice title=進捗ステージを付けた（{row}行目）::{before} → {stage} ｜ {url}")


if __name__ == "__main__":
    main()
