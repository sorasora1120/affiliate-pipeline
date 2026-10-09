"""
ワーカー提案マッチング エントリポイント

実行フロー:
  1. スプレッドシートの「未チェック」案件から、対象カテゴリ・予算あり・
     除外キーワードなしのものを抜き出す（依頼者情報は収集時=main.pyで
     取得済みのシートの値をそのまま読む。ここではライブ取得しない。
     CrowdWorksはクラウドから直接アクセスできないため必須の制約）
  2. 案件ごとに「自分用の要点／ワーカーへの交渉メッセージ／クライアントへの
     提案文下書き」の3点セットをDiscordに通知（1案件=1メッセージ）し、
     同じ内容をスプレッドシートの列にも書き込む（Discordが埋もれても
     シート側で必ず確認できるようにする）
  3. 通知した案件はステータスを「提案済み」に更新し、次回以降は対象外にする
"""
import logging
import os
import sys

import config
from src import sheet_lock
from src.expiry_checker import CLOSED_STATUS, find_closed_rows
from src.notifier import notify_discord, notify_error
from src.sheets_writer import SheetsWriter
from src.worker_matcher import red_flag
from src.worker_matcher import (
    BELOW_BUDGET_STATUS,
    EXCLUDED_KEYWORD_STATUS,
    PROPOSED_STATUS,
    find_candidates,
    format_combined_message,
    pick_wish_sentence,
    proposal_and_worker_message,
    review_proposed_rows,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run() -> None:
    # check_expired_main.pyと同じ行を同時に書き換えると、片方が削除した後に
    # もう片方が古い行番号のまま書き込んで「exceeds grid limits」エラーになる
    # （2026-08-15発覚、CrowdWorksの自動チェックと手動でのマッチング実行が重なり
    # 339件中29件の更新が実際に失敗した）。同じロックを共有して排他する。
    if not sheet_lock.acquire():
        logger.warning("別のシート書き込み処理が実行中のため、今回はスキップします")
        return
    try:
        _run_locked()
    finally:
        sheet_lock.release()


def _run_locked() -> None:
    logger.info("=== ワーカー提案マッチング 開始 ===")

    if not config.GOOGLE_SHEET_ID or not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_JSON が未設定です")

    sheet = SheetsWriter(
        sheet_id=config.GOOGLE_SHEET_ID,
        service_account_json=config.GOOGLE_SERVICE_ACCOUNT_JSON,
        worksheet_name=config.GOOGLE_WORKSHEET_NAME,
    )
    rows = sheet.all_records()

    _review_existing_proposals(sheet, rows)

    candidates, below_budget_rows, excluded_keyword_rows = find_candidates(
        rows,
        target_categories=config.WORKER_MATCH_CATEGORIES,
        excluded_keywords=config.WORKER_MATCH_EXCLUDE_KEYWORDS,
        min_budget_yen=config.WORKER_MATCH_MIN_BUDGET_YEN,
        margin_percent=config.WORKER_MATCH_MARGIN_PERCENT,
        margin_min_yen=config.WORKER_MATCH_MARGIN_MIN_YEN,
        margin_max_yen=config.WORKER_MATCH_MARGIN_MAX_YEN,
    )
    logger.info("マッチング候補: %d件", len(candidates))

    if candidates:
        # マッチングした直後に実際のページを開いて生存確認する（2026-08-15、
        # 「この抽出する過程で期限も見れないの？」との指摘を受けて統合。それまでは
        # 別工程（check_expired_main.py）が数時間後に確認するまでの間、実際には
        # もう募集終了している案件でも「提案済み」としてそのまま通知・表示され
        # 続けていた。ここで一緒に確認すれば、生きている案件しか提案済みにならない）。
        page_info: dict[int, dict] = {}
        closed_rows, deadlines = find_closed_rows([(c["row"], c["url"]) for c in candidates], page_info)
        if page_info:
            # 応募者数（S列）と募集文（T列）を最新の値に更新する。募集文は提案文の
            # 「募集文に沿った一言」に使う（2026-10-08）
            sheet.worksheet.batch_update(
                [{"range": f"S{row}:T{row}", "values": [[d["applicants"], d["description"]]]}
                 for row, d in page_info.items()],
                value_input_option="RAW",
            )
            logger.info("%d件の応募者数・募集文を更新しました（募集文あり%d件）", len(page_info),
                        sum(1 for d in page_info.values() if d["description"]))
            for c in candidates:
                desc = page_info.get(c["row"], {}).get("description")
                if desc:
                    c["description"] = desc
                if c["row"] in page_info:
                    c["applicants"] = page_info[c["row"]].get("applicants")
        flagged = [(c["row"], red_flag(c.get("description", ""))) for c in candidates]
        flagged = [(row, why) for row, why in flagged if why]
        if flagged:
            sheet.worksheet.batch_update(
                [{"range": f"A{row}", "values": [[RED_FLAG_STATUS]]} for row, _ in flagged],
                value_input_option="RAW",
            )
            for row, why in flagged:
                logger.info("要注意の案件を外しました row=%s（%s）", row, why)
            flagged_set = {row for row, _ in flagged}
            candidates = [c for c in candidates if c["row"] not in flagged_set]
        if closed_rows:
            closed_set = set(closed_rows)
            updates = [{"range": f"A{row}", "values": [[CLOSED_STATUS]]} for row in closed_rows]
            sheet.worksheet.batch_update(updates, value_input_option="RAW")
            logger.info("マッチング直後の生存確認で%d件が募集終了と判明、除外しました", len(closed_rows))
            candidates = [c for c in candidates if c["row"] not in closed_set]
        if deadlines:
            updates = [{"range": f"F{row}", "values": [[d]]} for row, d in deadlines.items()]
            sheet.worksheet.batch_update(updates, value_input_option="RAW")
            logger.info("%d件の締切を取得しました", len(deadlines))

    if below_budget_rows:
        # 予算未達の行を放置すると「未チェック」のまま残り、次回以降も毎回
        # 再評価され続け、ビューアの「確認前」タブにも未処理として出続ける
        # （2026-08-11発覚）。一括更新してステータスを進め、無限再評価を止める。
        try:
            updates = [
                {"range": f"A{row}", "values": [[BELOW_BUDGET_STATUS]]}
                for row in below_budget_rows
            ]
            sheet.worksheet.batch_update(updates, value_input_option="RAW")
            logger.info("%d件を「%s」に更新しました（予算未達）", len(below_budget_rows), BELOW_BUDGET_STATUS)
        except Exception as exc:
            logger.warning("予算未達行の一括更新に失敗しました: %s", exc)

    if excluded_keyword_rows:
        # 予算未達と同じ穴が除外キーワード側にもあった（2026-08-13発覚）。
        # 放置すると「未チェック」のまま無期限に滞留し続ける。
        try:
            updates = [
                {"range": f"A{row}", "values": [[EXCLUDED_KEYWORD_STATUS]]}
                for row in excluded_keyword_rows
            ]
            sheet.worksheet.batch_update(updates, value_input_option="RAW")
            logger.info(
                "%d件を「%s」に更新しました（除外キーワード）",
                len(excluded_keyword_rows),
                EXCLUDED_KEYWORD_STATUS,
            )
        except Exception as exc:
            logger.warning("除外キーワード行の一括更新に失敗しました: %s", exc)

    if not candidates:
        if os.getenv("QUIET") != "1":
            notify_discord("ワーカーに提案できる新規案件はありませんでした。")
        return

    sent = 0
    for c in candidates:
        try:
            proposal_text, worker_text = proposal_and_worker_message(c)

            ok = notify_discord(format_combined_message(c))
            if not ok:
                # Discord送信が1通でも失敗した案件はシートも更新しない。
                # 「未チェック」のまま残せば次回実行時に自動的に再送されるので、
                # 送信失敗＝内容が消える、という事態を防ぐ。
                logger.warning("Discord通知が一部失敗したため未チェックのまま残します (row=%s)", c.get("row"))
                continue
            # 詳細書き込みとステータス更新を1回のAPI呼び出しにまとめる
            # （2026-08-15、大量マッチングでSheets APIの書き込みレート制限に
            # 頻繁に当たっていたため、1件あたりのリクエスト数を半分にした）
            sheet.update_candidate_details_and_status(
                c["row"], c["margin"], c["quote"], worker_text, proposal_text, PROPOSED_STATUS
            )
            sent += 1
        except Exception as exc:
            # 1件の通知/更新失敗で残り全件が止まらないようにする
            # （長時間放置される想定のため、1件の異常で通知が止まるのが一番困る）
            logger.warning("案件の通知に失敗しました (row=%s): %s", c.get("row"), exc)

    logger.info("%d/%d件を「%s」に更新しました", sent, len(candidates), PROPOSED_STATUS)
    _notify_hot(candidates)


# 募集文に危ないサイン（成果報酬・外部でのやり取り・怪しい勧誘）があった案件のステータス
RED_FLAG_STATUS = "対象外（要注意）"


# 応募者がこの人数以下の新着は「今すぐ応募」として別に知らせる（2026-10-08）。
# 200件送って返信3件だったため、募集が出てすぐ・応募者が少ないうちに出せるようにする
HOT_MAX_APPLICANTS = 5


def _notify_hot(candidates: list[dict]) -> None:
    hot = []
    for c in candidates:
        try:
            n = int(str(c.get("applicants", "")).strip())
        except ValueError:
            continue
        if n <= HOT_MAX_APPLICANTS:
            hot.append((n, c))
    if not hot:
        return
    hot.sort(key=lambda x: x[0])
    lines = [f"🔥 今すぐ応募したい新着 {len(hot)}件（応募者が少ない順）"]
    for n, c in hot[:10]:
        amount = f"{c['amount']:,}円" if c.get("amount") else "予算は見積り希望"
        lines.append(f"・応募{n}人｜{c['title']}｜{amount}\n  {c['url']}")
    lines.append("ビューアの「送れる案件」から提案文をコピーして応募してね")
    notify_discord("\n".join(lines))


def _review_existing_proposals(sheet: SheetsWriter, rows: list[dict]) -> None:
    """未着手の「提案済み」行から無関係な案件を外し、残りの行の金額・提案文を
    最新の基準とテンプレートで付け直す。それぞれ1回のbatch_updateにまとめる（1行ずつ書くと
    Sheets APIの書き込みレート制限に当たるため）。"""
    irrelevant_rows, below_budget_rows, refreshed = review_proposed_rows(
        rows,
        excluded_keywords=config.WORKER_MATCH_EXCLUDE_KEYWORDS,
        min_budget_yen=config.WORKER_MATCH_MIN_BUDGET_YEN,
        margin_percent=config.WORKER_MATCH_MARGIN_PERCENT,
        margin_min_yen=config.WORKER_MATCH_MARGIN_MIN_YEN,
        margin_max_yen=config.WORKER_MATCH_MARGIN_MAX_YEN,
    )
    for target_rows, status, what in ((irrelevant_rows, EXCLUDED_KEYWORD_STATUS, "無関係な"),
                                      (below_budget_rows, BELOW_BUDGET_STATUS, "最低予算に届かない")):
        if not target_rows:
            continue
        try:
            sheet.worksheet.batch_update(
                [{"range": f"A{row}", "values": [[status]]} for row in target_rows],
                value_input_option="RAW",
            )
            logger.info("提案済みのうち%s%d件を「%s」に戻しました", what, len(target_rows), status)
        except Exception as exc:
            logger.warning("%s提案済み行の更新に失敗しました: %s", what, exc)
    if refreshed:
        try:
            updates = []
            for c in refreshed:
                proposal_text, worker_text = proposal_and_worker_message(c)
                # 募集文から拾った一言を確認できるようにログに残す
                logger.info("一言 row=%s: %s", c["row"], pick_wish_sentence(c.get("description", "")) or "（なし）")
                updates.append({
                    "range": f"M{c['row']}:P{c['row']}",
                    "values": [[c["margin"], c["quote"], worker_text, proposal_text]],
                })
            sheet.worksheet.batch_update(updates, value_input_option="RAW")
            logger.info("提案済み%d件の金額・提案文を付け直しました", len(refreshed))
        except Exception as exc:
            logger.warning("提案済み行の付け直しに失敗しました: %s", exc)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.exception("ワーカー提案マッチングが予期しないエラーで終了しました")
        notify_error(exc, "ワーカー提案マッチング 致命的エラー")
        sys.exit(1)
