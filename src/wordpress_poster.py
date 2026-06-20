"""
WordPress REST API を使って記事を自動投稿するモジュール。

認証方式: Application Passwords（WordPress 5.6 以降）
設定方法: WordPress 管理画面 → ユーザー → プロフィール → アプリケーションパスワード
"""

import logging
import os

import requests
from requests.auth import HTTPBasicAuth

from .article_writer import Article

logger = logging.getLogger(__name__)


class WordPressPoster:
    def __init__(self) -> None:
        base = os.environ["WP_SITE_URL"].rstrip("/")
        self.api_url = f"{base}/wp-json/wp/v2"
        self.auth = HTTPBasicAuth(
            os.environ["WP_USERNAME"],
            os.environ["WP_APP_PASSWORD"],   # アプリケーションパスワード（スペース含む文字列のまま使用可）
        )
        self.default_status = os.environ.get("WP_POST_STATUS", "draft")  # draft / publish
        self.default_category_id = int(os.environ.get("WP_CATEGORY_ID", "1"))

    def post(self, article: Article) -> dict:
        tag_ids = self._get_or_create_tags(article.tags)
        payload = {
            "title": article.title,
            "content": self._markdown_to_blocks(article.body_markdown),
            "excerpt": article.excerpt,
            "status": self.default_status,
            "categories": [self.default_category_id],
            "tags": tag_ids,
            "meta": {
                # SEO プラグイン（Yoast / RankMath）向け
                "_yoast_wpseo_metadesc": article.excerpt,
                "rank_math_description": article.excerpt,
            },
        }

        resp = requests.post(
            f"{self.api_url}/posts",
            json=payload,
            auth=self.auth,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(
            "投稿完了: ID=%s  URL=%s  ステータス=%s",
            result.get("id"),
            result.get("link"),
            result.get("status"),
        )
        return result

    # ------------------------------------------------------------------
    # タグ管理
    # ------------------------------------------------------------------

    def _get_or_create_tags(self, tag_names: list[str]) -> list[int]:
        ids: list[int] = []
        for name in tag_names:
            tag_id = self._find_tag(name) or self._create_tag(name)
            if tag_id:
                ids.append(tag_id)
        return ids

    def _find_tag(self, name: str) -> int | None:
        resp = requests.get(
            f"{self.api_url}/tags",
            params={"search": name, "per_page": 5},
            auth=self.auth,
            timeout=10,
        )
        resp.raise_for_status()
        for tag in resp.json():
            if tag["name"] == name:
                return tag["id"]
        return None

    def _create_tag(self, name: str) -> int | None:
        resp = requests.post(
            f"{self.api_url}/tags",
            json={"name": name},
            auth=self.auth,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return resp.json().get("id")
        logger.warning("タグ作成失敗: %s  %s", name, resp.text[:200])
        return None

    # ------------------------------------------------------------------
    # Markdown → WordPress ブロックエディタ用 HTML
    # ------------------------------------------------------------------

    @staticmethod
    def _markdown_to_blocks(markdown: str) -> str:
        """
        最低限の Markdown → HTML 変換。
        python-markdown ライブラリが使えない環境向けに自前実装。
        """
        try:
            import markdown as md_lib
            return md_lib.markdown(
                markdown,
                extensions=["tables", "fenced_code", "nl2br"],
            )
        except ImportError:
            pass

        # フォールバック: 見出し・段落のみ変換
        import re
        lines = markdown.split("\n")
        html_lines: list[str] = []
        for line in lines:
            if line.startswith("### "):
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("| "):
                html_lines.append(line)   # テーブルはそのまま（要プラグイン）
            elif line.strip() == "":
                html_lines.append("")
            else:
                # **bold** → <strong>
                line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
                html_lines.append(f"<p>{line}</p>")
        return "\n".join(html_lines)
