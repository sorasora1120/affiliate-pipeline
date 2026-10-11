"""一時：ランサーズの robots.txt と、一覧ページがもう一度だけ読めるかを確かめる（2026-10-11）。確かめたら消す。"""
import urllib.request


def note(title: str, msg: str) -> None:
    msg = msg.replace("%", "%25").replace("\r", "").replace("\n", " ⏎ ")
    print(f"::notice title={title}::{msg[:3000]}")


for name, url in [("robots.txt", "https://www.lancers.jp/robots.txt"), ("一覧web", "https://www.lancers.jp/work/search/web?open=1")]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (affiliate-pipeline probe)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            note(f"{name} {r.status}", body[:2500] if name == "robots.txt" else f"{len(body)}文字 / 案件リンク {body.count('/work/detail/')}個")
    except urllib.error.HTTPError as e:
        note(f"{name} {e.code}", (e.read() or b"").decode("utf-8", "replace")[:600])
    except Exception as exc:
        note(f"{name} 失敗", repr(exc)[:300])
