"""一時：ランサーズの robots.txt と、一覧ページがもう一度だけ読めるかを確かめる（2026-10-11）。確かめたら消す。"""
import sys
import urllib.error
import urllib.request

print("::notice title=probe start::ok", flush=True)


def note(title: str, msg: str) -> None:
    msg = msg.replace("%", "%25").replace("\r", "").replace("\n", " | ")
    print(f"::notice title={title}::{msg[:2500]}", flush=True)


for name, url in [("robots", "https://www.lancers.jp/robots.txt"), ("list", "https://www.lancers.jp/work/search/web?open=1")]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (affiliate-pipeline probe)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            note(f"{name} {r.status}", body[:2400] if name == "robots" else f"{len(body)} chars, detail links {body.count('/work/detail/')}")
    except urllib.error.HTTPError as e:
        note(f"{name} HTTP {e.code}", (e.read() or b"").decode("utf-8", "replace")[:500])
    except Exception as exc:
        note(f"{name} error", repr(exc)[:300])
sys.stdout.flush()
