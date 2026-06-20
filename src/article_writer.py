"""
Claude API を使って SEO 最適化「課題解決型比較記事」を生成するモジュール。
"""

import logging
import os
from dataclasses import dataclass

import anthropic

from .scraper import Campaign

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096


@dataclass
class Article:
    title: str
    body_markdown: str
    excerpt: str
    tags: list[str]
    campaign: Campaign


class ArticleWriter:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def write(self, campaign: Campaign) -> Article:
        logger.info("記事生成中: %s", campaign.service_name)

        # まずキーワード・ターゲット・訴求ポイントを抽出
        meta = self._extract_meta(campaign)
        campaign.appeal_points = meta["appeal_points"]
        campaign.target_audience = meta["target_audience"]

        # 本文生成
        body = self._generate_body(campaign, meta)
        title = self._generate_title(campaign, meta)
        excerpt = self._generate_excerpt(body)
        tags = meta.get("tags", [campaign.service_name])

        return Article(
            title=title,
            body_markdown=body,
            excerpt=excerpt,
            tags=tags,
            campaign=campaign,
        )

    # ------------------------------------------------------------------
    # メタ情報抽出
    # ------------------------------------------------------------------

    def _extract_meta(self, campaign: Campaign) -> dict:
        prompt = f"""以下のサービス情報を分析し、JSON 形式で返してください。

サービス名: {campaign.service_name}
説明文: {campaign.description}
報酬額: {campaign.reward_amount:,}円

出力形式（必ずこの JSON のみ、コードブロック不要）:
{{
  "appeal_points": ["訴求ポイント1", "訴求ポイント2", "訴求ポイント3"],
  "target_audience": "主なターゲット層（例: 20〜30代の会社員）",
  "main_problem": "このサービスが解決する主な課題",
  "competitors": ["競合サービス1", "競合サービス2"],
  "tags": ["タグ1", "タグ2", "タグ3"]
}}"""

        resp = self.client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        try:
            return json.loads(resp.content[0].text)
        except Exception:
            return {
                "appeal_points": [campaign.description[:50]],
                "target_audience": "一般ユーザー",
                "main_problem": "コスト・利便性の課題",
                "competitors": [],
                "tags": [campaign.service_name],
            }

    # ------------------------------------------------------------------
    # 記事本文生成
    # ------------------------------------------------------------------

    def _generate_body(self, campaign: Campaign, meta: dict) -> str:
        competitors_str = "、".join(meta.get("competitors", [])) or "他社サービス"
        appeal_str = "\n".join(f"- {p}" for p in campaign.appeal_points)

        prompt = f"""あなたはSEOに精通したコンテンツライターです。
以下の情報をもとに、**課題解決型比較記事** を Markdown で執筆してください。

## 記事情報
- 対象サービス: {campaign.service_name}
- ターゲット読者: {campaign.target_audience}
- 解決する課題: {meta.get('main_problem', '')}
- 訴求ポイント:
{appeal_str}
- 比較対象: {competitors_str}

## 記事構成の要件
1. **H2 見出しを5〜7個**使い、読者の検索意図に沿った構成にする
2. **冒頭150字**で読者の悩みに共感し、記事で解決できると示す
3. **比較表**（Markdown テーブル）を1つ入れ、{campaign.service_name} の優位性を示す
4. **FAQ セクション**（よくある質問 3〜5問）を末尾に入れる
5. **CTA（行動喚起）**を最後に自然な形で入れる
6. 文字数: 2,000〜3,000字を目安にする
7. キーワードを自然に含める（詰め込みすぎない）

Markdown のみを出力し、説明文は不要です。"""

        resp = self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    # ------------------------------------------------------------------
    # タイトル・抜粋生成
    # ------------------------------------------------------------------

    def _generate_title(self, campaign: Campaign, meta: dict) -> str:
        prompt = f"""以下のサービスについて、SEO タイトルを1行だけ生成してください。

サービス名: {campaign.service_name}
ターゲット: {campaign.target_audience}
課題: {meta.get('main_problem', '')}

条件:
- 32字以内
- 数字・「比較」「おすすめ」「評判」などのパワーワードを使う
- タイトルのみ出力（前後の説明不要）"""

        resp = self.client.messages.create(
            model=MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    def _generate_excerpt(self, body: str) -> str:
        # 本文冒頭から最初の段落を抜粋として使う（120〜160字）
        lines = [l.strip() for l in body.split("\n") if l.strip() and not l.startswith("#")]
        excerpt = lines[0] if lines else ""
        return excerpt[:160]
