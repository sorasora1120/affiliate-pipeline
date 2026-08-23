"""
Google Gemini API を使って SEO 最適化「課題解決型比較記事」を生成するモジュール。
Gemini が使えない場合は Groq にフォールバック。
"""

import json
import logging
import os
from dataclasses import dataclass

from .scraper import Campaign

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    body_markdown: str
    excerpt: str
    tags: list[str]
    campaign: Campaign


def _make_gemini_client():
    from google import genai
    from google.genai import types as gtypes
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return None, None
    try:
        client = genai.Client(
            api_key=key,
            http_options={"api_version": "v1"},
        )
        return client, gtypes
    except Exception:
        return None, None


def _ask_gemini(client, gtypes, prompt: str) -> str:
    safety_off = [
        gtypes.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        gtypes.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        gtypes.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        gtypes.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]
    for model in ("gemini-3.6-flash", "gemini-2.0-flash", "gemini-2.5-flash"):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=gtypes.GenerateContentConfig(safety_settings=safety_off),
            )
            return resp.text.strip()
        except Exception as e:
            logger.warning("Gemini %s 失敗: %s", model, e)
    raise RuntimeError("全Geminiモデル失敗")


def _ask_groq(prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )
    return resp.choices[0].message.content.strip()


class ArticleWriter:
    def __init__(self) -> None:
        self._gemini_client, self._gtypes = _make_gemini_client()
        self._use_groq = not self._gemini_client or not os.environ.get("GEMINI_API_KEY")
        if self._use_groq:
            logger.info("Groq モードで動作")
        else:
            logger.info("Gemini モードで動作")

    def _ask(self, prompt: str) -> str:
        if not self._use_groq:
            try:
                return _ask_gemini(self._gemini_client, self._gtypes, prompt)
            except Exception as e:
                logger.warning("Gemini全滅、Groqにフォールバック: %s", e)
                self._use_groq = True
        return _ask_groq(prompt)

    def write(self, campaign: Campaign) -> Article:
        logger.info("記事生成中: %s", campaign.service_name)
        meta = self._extract_meta(campaign)
        campaign.appeal_points = meta["appeal_points"]
        campaign.target_audience = meta["target_audience"]
        body = self._generate_body(campaign, meta)
        title = self._generate_title(campaign, meta)
        excerpt = self._generate_excerpt(body)
        tags = meta.get("tags", [campaign.service_name])
        return Article(title=title, body_markdown=body, excerpt=excerpt, tags=tags, campaign=campaign)

    def _extract_meta(self, campaign: Campaign) -> dict:
        prompt = f"""以下のサービス情報を分析し、JSON 形式のみで返してください（コードブロック不要）。

サービス名: {campaign.service_name}
説明文: {campaign.description}
報酬額: {campaign.reward_amount:,}円

出力形式:
{{"appeal_points": ["訴求ポイント1", "訴求ポイント2", "訴求ポイント3"], "target_audience": "ターゲット層", "main_problem": "解決する課題", "competitors": ["競合1", "競合2"], "tags": ["タグ1", "タグ2", "タグ3"]}}"""
        try:
            text = self._ask(prompt)
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception:
            return {"appeal_points": [campaign.description[:50]], "target_audience": "一般ユーザー",
                    "main_problem": "コスト・利便性の課題", "competitors": [], "tags": [campaign.service_name]}

    def _generate_body(self, campaign: Campaign, meta: dict) -> str:
        competitors_str = "、".join(meta.get("competitors", [])) or "他社サービス"
        appeal_str = "\n".join(f"- {p}" for p in campaign.appeal_points)
        prompt = f"""あなたはSEOに精通したコンテンツライターです。以下の情報をもとに課題解決型比較記事をMarkdownで執筆してください。

対象サービス: {campaign.service_name}
ターゲット読者: {campaign.target_audience}
解決する課題: {meta.get('main_problem', '')}
訴求ポイント:
{appeal_str}
比較対象: {competitors_str}

要件:
1. H2見出しを5〜7個使う
2. 冒頭150字で読者の悩みに共感する
3. 比較表（Markdownテーブル）を1つ入れる
4. FAQセクション（3〜5問）を末尾に入れる
5. CTAを最後に自然な形で入れる
6. 文字数: 2,000〜3,000字
7. Markdownのみ出力（説明文不要）"""
        return self._ask(prompt)

    def _generate_title(self, campaign: Campaign, meta: dict) -> str:
        prompt = f"""以下のサービスについてSEOタイトルを1行だけ生成してください。
サービス名: {campaign.service_name}
ターゲット: {campaign.target_audience}
課題: {meta.get('main_problem', '')}
条件: 32字以内、数字・「比較」「おすすめ」などのパワーワードを使う。タイトルのみ出力。"""
        return self._ask(prompt)

    def _generate_excerpt(self, body: str) -> str:
        lines = [l.strip() for l in body.split("\n") if l.strip() and not l.startswith("#")]
        return (lines[0] if lines else "")[:160]
