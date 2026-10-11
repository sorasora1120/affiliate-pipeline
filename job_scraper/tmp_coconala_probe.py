"""一時：ココナラの仕事依頼の一覧が GitHub Actions から読めるかを確かめる（2026-10-11）。確かめたら消す。"""
import re
import urllib.error
import urllib.parse
import urllib.request


def note(title: str, msg: str) -> None:
    msg = re.sub(r"[^0-9A-Za-z /_.?*=&\-|]", "_", msg)
    print(f"::notice title={title}::{msg[:1500]}", flush=True)


targets = [("robots", "https://coconala.com/robots.txt"),
           ("requests", "https://coconala.com/requests?keyword=" + urllib.parse.quote("ホームページ制作"))]
for name, url in targets:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        code, body = e.code, (e.read() or b"").decode("utf-8", "replace")
    except Exception as exc:
        code, body = 0, repr(exc)
    links = len(set(re.findall(r"/requests/(\d+)", body)))
    note(f"{name} status", f"{code} len={len(body)} request_links={links}")
    if name == "robots":
        rules = [l.strip().replace(":", "=") for l in body.splitlines() if re.match(r"(?i)\s*(user-agent|disallow|allow)", l)]
        hits = [r for r in rules if "request" in r.lower() or r.lower().startswith("user-agent")]
        note("robots requests rules", " | ".join(hits[:40]) or "none")
