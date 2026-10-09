"""ビューア（dispatch-viewer）の最新版のコミットSHAを、スプレッドシートの「設定」タブ B1 に書く。

2026-10-09追加。学校のネットワークで github.io / github.com が開けないため、ビューアはコミット固定の
rawcdn.githack.com のURLで開いていて、ビューアを直すたびに新しいリンクを渡していた（「毎回新しいリンクを
開くのがめんどくさい」）。ビューア（index.html / sales.html）は開いた時にこのセルを読み、自分より新しい版が
あれば自動でそちらへ移る。github.com はビューアからは読めないので、ビューアが読めるスプレッドシートに置く。

worker_match.yml の最後（収集のたび）と viewer_version.yml（ビューアを直した直後に手動）から動く。
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone

import gspread
from google.oauth2.service_account import Credentials

REPO = "sorasora1120/dispatch-viewer"
TAB = "設定"
JST = timezone(timedelta(hours=9))


def latest_sha() -> str:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/commits/main",
        headers={"Accept": "application/vnd.github.sha", "User-Agent": "affiliate-pipeline"},
    )
    token = os.getenv("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    sha = urllib.request.urlopen(req, timeout=30).read().decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError(f"コミットSHAの形ではない返事でした: {sha[:80]!r}")
    return sha


def main() -> None:
    sha = latest_sha()
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    book = gspread.authorize(creds).open_by_key(os.environ["GOOGLE_SHEET_ID"])
    try:
        ws = book.worksheet(TAB)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=TAB, rows=10, cols=3)
    if ws.acell("B1").value == sha:
        print(f"ビューアの最新版は記録済み: {sha}")
        return
    ws.update(range_name="A1:C1", values=[["viewer_sha", sha, datetime.now(JST).strftime("%Y-%m-%d %H:%M")]])
    print(f"::notice title=ビューアの最新版を記録::{sha}")


if __name__ == "__main__":
    main()
