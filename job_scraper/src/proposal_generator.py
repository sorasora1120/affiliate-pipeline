"""
提案文の下書き生成（テンプレートに案件タイトルを差し込むだけ）。

送信は必ず本人が行う前提のため、ここでは「下書きを用意する」ところまでを担当する。
"""
from .models import JobPosting

DEFAULT_TEMPLATE = """はじめまして。「{title}」の案件を拝見し、ご提案させていただきます。

海外の実績豊富なクリエイターと連携し、高品質な制作物を短納期・低コストでご提供可能です。
過去の制作実績や具体的な進行スケジュールについては、メッセージにてご案内させていただきます。

ご検討のほど、よろしくお願いいたします。
"""

CATEGORY_TEMPLATES: dict[str, str] = {
    "ロゴ": DEFAULT_TEMPLATE,
    "ロゴデザイン": DEFAULT_TEMPLATE,
    "動画編集": DEFAULT_TEMPLATE,
    "動画制作": DEFAULT_TEMPLATE,
    "サイト制作": DEFAULT_TEMPLATE,
    "ホームページ制作": DEFAULT_TEMPLATE,
    "ECサイト構築": DEFAULT_TEMPLATE,
}


def generate_proposal(job: JobPosting) -> str:
    template = CATEGORY_TEMPLATES.get(job.category, DEFAULT_TEMPLATE)
    return template.format(title=job.title)
