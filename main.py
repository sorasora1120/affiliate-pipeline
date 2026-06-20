"""
自動収益化パイプライン エントリポイント

実行フロー:
  1. A8.net からセルフバック案件を取得
  2. 各案件について Claude で記事を生成
  3. WordPress に投稿
  4. エラーは Discord に通知
"""

import logging
import os
import sys
import time

from src.article_writer import ArticleWriter
from src.notifier import notify_discord, notify_error
from src.scraper import A8Scraper
from src.wordpress_poster import WordPressPoster

# ---------------------------------------------------------------------------
# ロギング設定
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
MIN_REWARD = int(os.environ.get("MIN_REWARD_YEN", "5000"))
MAX_ARTICLES_PER_RUN = int(os.environ.get("MAX_ARTICLES_PER_RUN", "3"))
ARTICLE_INTERVAL_SECONDS = int(os.environ.get("ARTICLE_INTERVAL_SECONDS", "30"))


def run_pipeline() -> None:
    logger.info("=== 自動収益化パイプライン 開始 ===")
    notify_discord("パイプライン実行を開始しました。")

    # 1. スクレイピング
    logger.info("--- Step 1: A8.net スクレイピング ---")
    try:
        scraper = A8Scraper()
        campaigns = scraper.fetch_campaigns(min_reward=MIN_REWARD)
    except Exception as exc:
        notify_error(exc, "Step 1: A8.net スクレイピング失敗")
        raise

    if not campaigns:
        msg = f"報酬 {MIN_REWARD:,}円以上の案件が見つかりませんでした。パイプラインを終了します。"
        logger.info(msg)
        notify_discord(msg)
        return

    logger.info("%d 件の案件を取得（最大 %d 件を処理）", len(campaigns), MAX_ARTICLES_PER_RUN)
    targets = campaigns[:MAX_ARTICLES_PER_RUN]

    writer = ArticleWriter()
    poster = WordPressPoster()
    succeeded: list[str] = []
    failed: list[str] = []

    for i, campaign in enumerate(targets, 1):
        logger.info("--- [%d/%d] %s ---", i, len(targets), campaign.service_name)

        # 2. 記事生成
        try:
            article = writer.write(campaign)
        except Exception as exc:
            notify_error(exc, f"Step 2: 記事生成失敗 ({campaign.service_name})")
            failed.append(campaign.service_name)
            continue

        # 3. WordPress 投稿
        try:
            result = poster.post(article)
            succeeded.append(f"{campaign.service_name} → {result.get('link', '')}")
        except Exception as exc:
            notify_error(exc, f"Step 3: WordPress 投稿失敗 ({campaign.service_name})")
            failed.append(campaign.service_name)
            continue

        if i < len(targets):
            logger.info("次の案件まで %d 秒待機...", ARTICLE_INTERVAL_SECONDS)
            time.sleep(ARTICLE_INTERVAL_SECONDS)

    # 完了サマリー
    summary_lines = ["=== パイプライン完了 ==="]
    if succeeded:
        summary_lines.append(f"✅ 投稿成功 ({len(succeeded)}件):")
        summary_lines.extend(f"  - {s}" for s in succeeded)
    if failed:
        summary_lines.append(f"❌ 失敗 ({len(failed)}件): {', '.join(failed)}")
    summary = "\n".join(summary_lines)
    logger.info(summary)
    notify_discord(summary, is_error=bool(failed))


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as exc:
        logger.exception("パイプラインが予期しないエラーで終了しました")
        notify_error(exc, "パイプライン致命的エラー")
        sys.exit(1)
