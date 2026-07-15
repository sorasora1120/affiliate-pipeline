import json
import logging

import gspread
from google.oauth2.service_account import Credentials

from .models import JobPosting

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADER = [
    "ステータス", "プラットフォーム", "タイトル", "カテゴリ", "予算", "締切",
    "URL", "検出日時", "提案文（下書き）",
]


class SheetsWriter:
    def __init__(self, sheet_id: str, service_account_json: str, worksheet_name: str = "案件一覧") -> None:
        info = json.loads(service_account_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)

        try:
            self.worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            self.worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=len(HEADER))
            self.worksheet.append_row(HEADER)

        if self.worksheet.row_values(1) != HEADER:
            self.worksheet.update("A1", [HEADER])

    def existing_urls(self) -> set[str]:
        url_col_index = HEADER.index("URL") + 1
        values = self.worksheet.col_values(url_col_index)[1:]  # ヘッダーを除く
        return set(values)

    def append_jobs(self, jobs: list[JobPosting], proposals: dict[str, str]) -> None:
        if not jobs:
            return
        rows = [
            [
                "未チェック",
                job.platform,
                job.title,
                job.category,
                job.budget_text,
                job.deadline_text,
                job.url,
                job.detected_at,
                proposals.get(job.url, ""),
            ]
            for job in jobs
        ]
        self.worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        logger.info("スプレッドシートに %d 件追加しました", len(rows))
