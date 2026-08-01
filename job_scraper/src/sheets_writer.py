import json
import logging

import gspread
from google.oauth2.service_account import Credentials

from .models import JobPosting

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADER = [
    "ステータス", "プラットフォーム", "タイトル", "カテゴリ", "予算", "締切",
    "URL", "検出日時", "提案文（下書き）", "依頼者名", "評価", "実績件数",
    "利益目安（円）", "ワーカー提示額（円）", "ワーカー向けメッセージ", "クライアント提案文（詳細版）",
]

# 検出日時（H列）のvalue。日別タブのQUERY式で参照するため列位置を固定で持っておく
_DETECTED_AT_COL_INDEX = HEADER.index("検出日時") + 1  # 8 = H
_CANDIDATE_DETAIL_COLS = ["利益目安（円）", "ワーカー提示額（円）", "ワーカー向けメッセージ", "クライアント提案文（詳細版）"]
# 長文が入る列（0始まりインデックス）。折り返しで行が肥大化しないようクリップ表示にし、
# 内容に合わせたauto-resizeの対象からも外して固定幅にする
_LONG_TEXT_COLUMNS = ["提案文（下書き）", "ワーカー向けメッセージ", "クライアント提案文（詳細版）"]
_LONG_TEXT_INDICES_0BASED = [HEADER.index(c) for c in _LONG_TEXT_COLUMNS]


def _col_letter(index_1based: int) -> str:
    """1始まりの列番号をA〜Z1文字の列記号に変換する（列数が26を超える予定はないため簡易実装）。"""
    return chr(ord("A") + index_1based - 1)


def _apply_sheet_formatting(ws) -> None:
    """見やすさ対策: ヘッダー行固定、長文列はクリップ表示＆固定幅、それ以外は内容に合わせて自動調整。"""
    sheet_id = ws.id
    requests = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]
    for idx in _LONG_TEXT_INDICES_0BASED:
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": idx, "endIndex": idx + 1},
                "properties": {"pixelSize": 250},
                "fields": "pixelSize",
            }
        })
    ws.spreadsheet.batch_update({"requests": requests})

    long_ranges = [f"{_col_letter(idx + 1)}1:{_col_letter(idx + 1)}" for idx in _LONG_TEXT_INDICES_0BASED]
    ws.format(long_ranges, {"wrapStrategy": "CLIP"})

    # 短い列は内容に合わせて自動調整（長文列の間で分割されている区間ごとに実行）
    short_indices = sorted(set(range(len(HEADER))) - set(_LONG_TEXT_INDICES_0BASED))
    start = None
    for i, idx in enumerate(short_indices):
        if start is None:
            start = idx
        is_last = i == len(short_indices) - 1
        next_idx = short_indices[i + 1] if not is_last else None
        if is_last or next_idx != idx + 1:
            ws.columns_auto_resize(start, idx + 1)
            start = None


class SheetsWriter:
    def __init__(self, sheet_id: str, service_account_json: str, worksheet_name: str = "案件一覧") -> None:
        info = json.loads(service_account_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        client = gspread.authorize(creds)
        self.spreadsheet = client.open_by_key(sheet_id)

        try:
            self.worksheet = self.spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            self.worksheet = self.spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=len(HEADER))
            self.worksheet.append_row(HEADER)

        if self.worksheet.row_values(1) != HEADER:
            self.worksheet.update(range_name="A1", values=[HEADER])
            try:
                _apply_sheet_formatting(self.worksheet)
            except Exception as exc:
                logger.warning("マスターシートの書式設定に失敗しました: %s", exc)

    def existing_urls(self) -> set[str]:
        url_col_index = HEADER.index("URL") + 1
        values = self.worksheet.col_values(url_col_index)[1:]  # ヘッダーを除く
        return set(values)

    def all_records(self) -> list[dict]:
        return self.worksheet.get_all_records()

    def update_status(self, row_number: int, status: str) -> None:
        status_col = HEADER.index("ステータス") + 1
        self.worksheet.update_cell(row_number, status_col, status)

    def update_candidate_details(
        self,
        row_number: int,
        margin: int | None,
        quote: int | None,
        worker_message: str,
        client_proposal: str,
    ) -> None:
        """ワーカーマッチングで組み立てた4点セット（利益目安/ワーカー提示額/ワーカー向け
        メッセージ/クライアント提案文）をシート側にも書き込む。Discordが埋もれても
        シートを見れば同じ内容を確認できるようにする。"""
        start_col = HEADER.index(_CANDIDATE_DETAIL_COLS[0]) + 1
        end_col = HEADER.index(_CANDIDATE_DETAIL_COLS[-1]) + 1
        rng = f"{_col_letter(start_col)}{row_number}:{_col_letter(end_col)}{row_number}"
        values = [[
            margin if margin is not None else "見積り要相談",
            quote if quote is not None else "見積り要相談",
            worker_message,
            client_proposal,
        ]]
        self.worksheet.update(range_name=rng, values=values, value_input_option="USER_ENTERED")

    def ensure_daily_view(self, date_str: str) -> None:
        """指定日（YYYY-MM-DD）の案件だけを表示する日別タブを用意する。

        マスターシートの実体をコピーするのではなくQUERY式で参照するだけなので、
        後から依頼者情報やワーカー提案の内容が更新されても自動的に反映される。
        既に同名タブがあれば何もしない。

        注意: 検出日時は文字列としてlike比較しているため、append_jobsをUSER_ENTERED
        （Sheets側で自動的に日付型に変換されてしまう）で書いていた過去の行は対象外。
        この関数の導入以降にRAWで書き込まれた行のみが日別タブに表示される。
        """
        try:
            self.spreadsheet.worksheet(date_str)
            return
        except gspread.WorksheetNotFound:
            pass

        ws = self.spreadsheet.add_worksheet(title=date_str, rows=200, cols=len(HEADER))
        last_col = _col_letter(len(HEADER))
        detected_at_col = _col_letter(_DETECTED_AT_COL_INDEX)
        formula = (
            f"=QUERY('{self.worksheet.title}'!A1:{last_col}, "
            f"\"select * where Col{_DETECTED_AT_COL_INDEX} like '{date_str}%'\", 1)"
        )
        ws.update(range_name="A1", values=[[formula]], value_input_option="USER_ENTERED")
        try:
            _apply_sheet_formatting(ws)
        except Exception as exc:
            logger.warning("日別タブ「%s」の書式設定に失敗しました: %s", date_str, exc)
        logger.info("日別タブ「%s」を作成しました（%s列を検出日時として参照）", date_str, detected_at_col)

    def append_jobs(
        self,
        jobs: list[JobPosting],
        proposals: dict[str, str],
        client_info: dict[str, dict] | None = None,
    ) -> None:
        if not jobs:
            return
        client_info = client_info or {}
        rows = []
        for job in jobs:
            info = client_info.get(job.url, {})
            rows.append([
                "未チェック",
                job.platform,
                job.title,
                job.category,
                job.budget_text,
                job.deadline_text,
                job.url,
                job.detected_at,
                proposals.get(job.url, ""),
                info.get("client_name", ""),
                info.get("rating", ""),
                info.get("order_count", ""),
                "", "", "", "",
            ])
        # RAW指定: USER_ENTEREDだと「検出日時」列（"2026-08-01 11:25"のような文字列）が
        # Sheets側で日付シリアル値に自動変換されてしまい、日別タブのQUERY(...like...)による
        # 文字列一致が効かなくなる（実際にこれで日別タブが常に0件になるバグが発生した）。
        # RAWなら入力した文字列がそのままセルに入るため、like比較が正しく動く。
        self.worksheet.append_rows(rows, value_input_option="RAW")
        logger.info("スプレッドシートに %d 件追加しました", len(rows))
