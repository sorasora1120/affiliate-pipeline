"""一時：ランサーズの robots.txt と、一覧ページがもう一度だけ読めるかを確かめる（2026-10-11）。確かめたら消す。"""
import re
import urllib.error
import urllib.request


def note(title: str, msg: str) -> None:
    msg = re.sub(r"[^0-9A-Za-z /_.?*=&\-|]", "_", msg)  # 注釈を壊しそうな文字は全部 _ にする
    print(f"::notice title={title}::{msg[:1500]}", flush=True)


results = {}
for name, url in [("robots", "https://www.lancers.jp/robots.txt"), ("list", "https://www.lancers.jp/work/search/web?open=1")]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (affiliate-pipeline probe)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            results[name] = (r.status, r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        results[name] = (e.code, (e.read() or b"").decode("utf-8", "replace"))
    except Exception as exc:
        results[name] = (0, repr(exc))
for name, (code, body) in results.items():
    note(f"{name} status", f"{code} len={len(body)} detail_links={body.count('/work/detail/')}")
code, body = results["robots"]
rules = [l.strip().replace(":", "=") for l in body.splitlines() if re.match(r"(?i)\s*(user-agent|disallow|allow|crawl-delay)", l)]
for i in range(0, min(len(rules), 160), 20):
    note(f"robots {i // 20 + 1}", " | ".join(rules[i:i + 20]))
