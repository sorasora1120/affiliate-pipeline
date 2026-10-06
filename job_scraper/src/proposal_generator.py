"""
提案文の下書き生成（テンプレートに案件タイトルを差し込むだけ）。

送信は必ず本人が行う前提のため、ここでは「下書きを用意する」ところまでを担当する。

2026-10-06、「もっと採用されやすい文章にしたい」との要望を受けて改訂。
よくある「はじめまして、実績豊富なチームで〜」という定型挨拶は、依頼者側から
見ると量産テンプレートと分かりやすく埋もれやすいため、案件の予算・納期に
具体的に触れて「ちゃんと読んで提案している」ことが伝わる文面にした。
"""
from .models import JobPosting


def _condition_line(job: JobPosting) -> str:
    """予算・納期が分かっている場合のみ、それに触れる一文を作る（不明な場合は空文字）。"""
    bits = []
    if job.budget_text and job.budget_text != "不明":
        bits.append(f"ご予算{job.budget_text}")
    if job.deadline_text and job.deadline_text != "不明":
        bits.append(f"納期{job.deadline_text}")
    if not bits:
        return ""
    return "、".join(bits) + "で対応いたします。\n"


DEFAULT_TEMPLATE = """「{title}」を拝見し、ご提案いたします。

{category}を専門に対応しており、すぐに着手可能です。{condition_line}品質を落とさず、短納期・低コストでご提供できるのが強みです。

過去の制作実績や具体的な進行スケジュールは、やり取りの中で詳しくご案内いたします。ご不明な点があればお気軽にメッセージください。

ご検討のほど、よろしくお願いいたします。
"""

CATEGORY_TEMPLATES: dict[str, str] = {}


def generate_proposal(job: JobPosting) -> str:
    template = CATEGORY_TEMPLATES.get(job.category, DEFAULT_TEMPLATE)
    return template.format(
        title=job.title,
        category=job.category,
        condition_line=_condition_line(job),
    )
