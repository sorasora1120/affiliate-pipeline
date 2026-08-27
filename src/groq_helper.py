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
        models = client.models.list().data
        available = {m.id for m in models}
        logger.info("Groq利用可能モデル: %s", sorted(available))
        for model in _PREFERRED:
            if model in available:
                logger.info("Groqモデル選択: %s", model)
                return model
        # 優先リストになければcontext_windowが大きいllama/mixtralを選ぶ
        candidates = [m for m in models if "llama" in m.id.lower() or "mixtral" in m.id.lower()]
        if candidates:
            # context_windowが大きいものを優先
            best = max(candidates, key=lambda m: getattr(m, "context_window", 0))
            logger.info("Groqモデル自動選択: %s (context=%s)", best.id, getattr(best, "context_window", "?"))
            return best.id
    except Exception as e:
        logger.warning("モデルリスト取得失敗: %s", e)
    return _PREFERRED[-1]  # 最終フォールバック


def ask_groq(prompt: str, max_tokens: int = 4096, temperature: float = 0.7) -> str:
    """Groq APIでテキスト生成。max_tokensが大きすぎる場合は自動で下げて再試行。"""
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model = get_groq_model(client)
    current_prompt = prompt
    for tokens in (max_tokens, 2048, 1024, 512):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": current_prompt}],
                max_tokens=tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "max_tokens" in err or "context_window" in err:
                logger.warning("max_tokens=%d 失敗、縮小して再試行", tokens)
                continue
            if "reduce the length" in err or "too long" in err.lower():
                # プロンプト自体を半分に切って再試行
                current_prompt = current_prompt[:len(current_prompt) // 2]
                logger.warning("プロンプトが長すぎるため半分に切り詰め")
                continue
            raise
    raise RuntimeError("Groq全トークン数で失敗")
