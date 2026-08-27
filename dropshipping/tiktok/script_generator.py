"""
TikTok教育コンテンツ台本自動生成モジュール。
ターゲット: 30代働く女性 / テーマ: 目元・むくみ・美容ガジェットケア
"""

import os
import json
import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

BRAND_CONCEPT = "30代働く女性向け、疲れ・むくみケアガジェット専門"

CONTENT_THEMES = [
    "目疲れの原因TOP3（リモートワーク編）",
    "むくみ顔を撃退する朝3分ルーティン",
    "美容ガジェット選びで失敗しないポイント",
    "アイマッサージャーの正しい使い方と効果",
    "頭皮マッサージが顔のたるみに効く理由",
    "目の下のクマ・むくみの原因と対策",
    "寝る前3分でできるフェイスリフトマッサージ",
    "リンパを流すと顔が小さくなる仕組み",
    "美容家電を安く手に入れる方法",
    "仕事中にできる目元ストレッチ",
    "むくみやすい人の生活習慣チェックリスト",
    "フェイスローラーの正しい使い方",
    "30代から始めたい目元ケアの習慣",
    "コスパ最強の美容ガジェット3選",
    "温冷ケアで目元が劇的に変わる理由",
    "スキンケアより先にやるべき「むくみ取り」",
    "目が疲れると老けて見える理由",
    "ながら美容ガジェットで時短ケアする方法",
    "プロが教えるむくみが取れる顔マッサージ",
    "美容ガジェットを毎日続けられる仕組みの作り方",
]


@dataclass
class TikTokScript:
    title: str
    hook: str
    body: str
    cta: str
    hashtags: list[str]
    best_post_time: str
    theme: str
    video_style: str = ""


class ScriptGenerator:
    def __init__(self) -> None:
        self.api_key = os.environ["GROQ_API_KEY"]

    def generate(self, theme: str) -> TikTokScript:
        logger.info("台本生成中: %s", theme)
        raw = self._call_api(theme)
        return self._parse(raw, theme)

    def _call_api(self, theme: str) -> dict:
        prompt = f"""あなたは30代のリアルなOLで、TikTokで「疲れ・むくみケア」を発信している人物です。
AIっぽさを一切排除した、本物の人間が話すような台本をJSON形式で生成してください。

## テーマ
{theme}

## 絶対に守るルール（これを破るとAIっぽくなる）
- 整いすぎた構成NG（完璧な起承転結は使わない）
- 「〜なんです」「〜んですよ」の多用NG
- 教科書みたいな説明NG
- 「今日は〜について話します」みたいな宣言NG
- 結論から始めない（視聴者を引きつけてから話す）

## 人間っぽさを出すテクニック（必ず使う）
- 自分の失敗談や実体験を冒頭に入れる（「先週さ〜」「実は私も〜」「これ知ったとき正直ビビった」）
- 途中で言い直しや補足を入れる（「あ、ちゃんと説明すると〜」「語弊があるから言い直すと〜」）
- 視聴者への問いかけを入れる（「これ心当たりある人〜？」「やってる人いる？」）
- 感情の起伏をつける（驚き・共感・笑い・ちょっとした怒り）
- 具体的な状況を入れる（「夜10時にPC閉じた後に鏡見て〜」「会議前にトイレで顔見たら〜」）
- 「でも正直〜」「これ言うと怒られるかもだけど」などの本音感

## 口調
- タメ口〜ちょいため口混じりの丁寧語（友達に話す感じ）
- 「〜だよね」「〜じゃん」「〜だと思う」を自然に混ぜる
- 読点（、）多めで息継ぎを意識したリズム

## 出力形式（このJSONのみ、コードブロック不要）
{{
  "title": "動画タイトル（釣り感なし・30字以内・検索されそうな自然な言葉）",
  "hook": "最初の3秒（自分の体験か、共感を呼ぶ一言。「〜について話します」はNG）",
  "body": "本編台本（改行区切り・セリフ形式・60〜90秒・途中に問いかけや感情表現を入れる）",
  "cta": "締めのひと言（押しつけがましくない・自然な流れで保存orフォローを促す）",
  "hashtags": ["タグ1", "タグ2", "タグ3", "タグ4", "タグ5"],
  "best_post_time": "投稿推奨時間帯",
  "video_style": "撮影スタイルの提案（例: 洗面台の前でトーク・スマホ手持ちで歩きながら・テキストのみ等）"
}}"""

        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from src.groq_helper import ask_groq
        text = ask_groq(prompt, max_tokens=1500, temperature=0.8)

        import re
        # コードブロック除去
        text = re.sub(r"```(?:json)?", "", text).strip()
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(), strict=False)
            raise RuntimeError(f"JSON解析失敗: {text[:200]}")

    def _parse(self, raw: dict, theme: str) -> TikTokScript:
        return TikTokScript(
            title=raw.get("title", ""),
            hook=raw.get("hook", ""),
            body=raw.get("body", ""),
            cta=raw.get("cta", ""),
            hashtags=raw.get("hashtags", []),
            best_post_time=raw.get("best_post_time", "20:00〜22:00"),
            theme=theme,
            video_style=raw.get("video_style", ""),
        )

    def to_markdown(self, script: TikTokScript) -> str:
        hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in script.hashtags)
        return f"""# {script.title}

**テーマ:** {script.theme}
**投稿推奨時間:** {script.best_post_time}
**撮影スタイル:** {script.video_style}

---

## フック（最初3秒）
{script.hook}

---

## 本編
{script.body}

---

## CTA（締め）
{script.cta}

---

## ハッシュタグ
{hashtag_str}
"""
