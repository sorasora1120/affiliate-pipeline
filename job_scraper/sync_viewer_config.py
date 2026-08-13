"""docs/index.html（GitHub Pagesライブビューア）に埋め込んだ
WORKER_MATCH_CATEGORIES / WORKER_MATCH_EXCLUDE_KEYWORDSを、config.pyの
現在の値と同期する。

docs/index.htmlはブラウザから直接開かれる静的ページで、サーバー側の
config.pyを実行時に読むことはできない。そのため必要なリストをJS内に
ハードコードして持っている。config.pyを変更したのにこのファイルの
更新を忘れると、GitHub Pages版だけ古い判定基準で動き続けてしまう
（2026-08-11〜12に複数回、手作業での同期漏れが実際に起きた）。

使い方: config.pyを変更したら、このスクリプトを実行してdocs/index.htmlを
更新する。その後、公開リポジトリ（dispatch-viewer）へは別途API経由での
反映が必要（[[project_outsourcing_arbitrage]]参照、ローカルgit pushは
auto-modeにブロックされるため）。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config

DOCS_PATH = Path(__file__).parent.parent / "docs" / "index.html"


def _js_string_array(items: list[str], width: int = 90) -> str:
    """レビューしやすいよう、幅に収まる範囲で複数行に折り返す。"""
    lines: list[str] = []
    current = "  "
    for item in items:
        token = f'"{item}",'
        if len(current) + len(token) > width and current.strip():
            lines.append(current)
            current = "  "
        current += token
    if current.strip():
        lines.append(current)
    return "\n".join(lines)


def sync() -> bool:
    """docs/index.htmlのハードコードされた設定を更新する。変更があればTrueを返す。"""
    html = DOCS_PATH.read_text(encoding="utf-8")

    categories_js = "new Set([\n" + _js_string_array(sorted(config.WORKER_MATCH_CATEGORIES)) + "\n]);"
    new_html = re.sub(
        r"const WORKER_MATCH_CATEGORIES = new Set\(\[.*?\]\);",
        f"const WORKER_MATCH_CATEGORIES = {categories_js}",
        html,
        flags=re.DOTALL,
    )

    keywords_js = "[\n" + _js_string_array(config.WORKER_MATCH_EXCLUDE_KEYWORDS) + "\n];"
    new_html = re.sub(
        r"const WORKER_MATCH_EXCLUDE_KEYWORDS = \[.*?\];",
        f"const WORKER_MATCH_EXCLUDE_KEYWORDS = {keywords_js}",
        new_html,
        flags=re.DOTALL,
    )

    if new_html == html:
        print("docs/index.html は既に最新です（変更なし）")
        return False

    DOCS_PATH.write_text(new_html, encoding="utf-8")
    print(f"docs/index.html を更新しました（カテゴリ{len(config.WORKER_MATCH_CATEGORIES)}件 / 除外語{len(config.WORKER_MATCH_EXCLUDE_KEYWORDS)}件）")
    return True


if __name__ == "__main__":
    sync()
