"""Groq APIのモデルを動的に選択するヘルパー"""
import logging
import os

logger = logging.getLogger(__name__)

# 優先モデル順（古いものから新しいものへフォールバック）
_PREFERRED = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama3-70b-8192",
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
]


def get_groq_model(client) -> str:
    """利用可能なGroqモデルを返す"""
    try:
        available = {m.id for m in client.models.list().data}
        for model in _PREFERRED:
            if model in available:
                logger.info("Groqモデル選択: %s", model)
                return model
        # 優先リストになければ最初のchat対応モデルを使う
        for m in client.models.list().data:
            if "llama" in m.id.lower() or "mixtral" in m.id.lower():
                logger.info("Groqモデル自動選択: %s", m.id)
                return m.id
    except Exception as e:
        logger.warning("モデルリスト取得失敗: %s", e)
    return _PREFERRED[-1]  # 最終フォールバック


def ask_groq(prompt: str, max_tokens: int = 4096, temperature: float = 0.7) -> str:
    """Groq APIでテキスト生成"""
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model = get_groq_model(client)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()
