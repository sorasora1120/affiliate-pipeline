"""
はてなブログ AtomPub API を使って記事を自動投稿するモジュール。

APIキーの取得場所:
  はてなブログ管理画面 → 設定 → 詳細設定 → AtomPub → APIキー
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth

from .article_writer import Article

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
ATOM_NS = "http://www.w3.org/2005/Atom"
APP_NS  = "http://www.w3.org/2007/app"


class WordPressPoster:  # 名前はそのまま（main.py の import を変えなくて済む）
    def __init__(self) -> None:
        self.hatena_id   = os.environ["HATENA_ID"]
        self.blog_domain = os.environ["HATENA_BLOG_DOMAIN"]   # sorajima112.hatenablog.com
        self.api_key     = os.environ["HATENA_API_KEY"]
        self.draft       = os.environ.get("HATENA_DRAFT", "yes")   # yes=下書き / no=公開
        self.endpoint    = (
            f"https://blog.hatena.ne.jp/{self.hatena_id}"
            f"/{self.blog_domain}/atom/entry"
        )
        self.auth = HTTPBasicAuth(self.hatena_id, self.api_key)

    def post(self, article: Article) -> dict:
        xml_bytes = self._build_xml(article)
        resp = requests.post(
            self.endpoint,
            data=xml_bytes,
            auth=self.auth,
            headers={"Content-Type": "application/atom+xml; charset=utf-8"},
            timeout=30,
        )
        resp.raise_for_status()

        url = self._parse_url(resp.text)
        status = "draft" if self.draft == "yes" else "published"
        logger.info("投稿完了: %s  (%s)", url, status)
        return {"url": url, "status": status}

    # ------------------------------------------------------------------
    # XML 生成
    # ------------------------------------------------------------------

    def _build_xml(self, article: Article) -> bytes:
        ET.register_namespace("",    ATOM_NS)
        ET.register_namespace("app", APP_NS)

        entry = Element(f"{{{ATOM_NS}}}entry")

        title = SubElement(entry, f"{{{ATOM_NS}}}title")
        title.text = article.title

        updated = SubElement(entry, f"{{{ATOM_NS}}}updated")
        updated.text = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")

        content = SubElement(entry, f"{{{ATOM_NS}}}content")
        content.set("type", "text/x-markdown")
        content.text = article.body_markdown

        summary = SubElement(entry, f"{{{ATOM_NS}}}summary")
        summary.text = article.excerpt

        for tag in article.tags:
            cat = SubElement(entry, f"{{{ATOM_NS}}}category")
            cat.set("term", tag)

        control = SubElement(entry, f"{{{APP_NS}}}control")
        draft_el = SubElement(control, f"{{{APP_NS}}}draft")
        draft_el.text = self.draft

        return b'<?xml version="1.0" encoding="utf-8"?>\n' + tostring(entry, encoding="unicode").encode("utf-8")

    @staticmethod
    def _parse_url(xml_text: str) -> str:
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": ATOM_NS}
            link = root.find("atom:link[@rel='alternate']", ns)
            if link is not None:
                return link.get("href", "")
        except Exception:
            pass
        return ""
