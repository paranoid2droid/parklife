"""One-shot: download the four prefecture-level park list pages so we can
hand-write per-prefecture extractors with full visibility into the HTML.

Output: data/raw/_seeds/<prefecture>.html

Uses curl_cffi to impersonate a real browser TLS fingerprint — some Japanese
gov sites reject Python's default TLS handshake.
"""

from __future__ import annotations

from pathlib import Path

from curl_cffi import requests

PAGES: dict[str, str] = {
    "tokyo":     "https://www.tokyo-park.or.jp/park_list/",
    "kanagawa":  "http://www.kanagawa-kouen.jp/parklist/list.html",
    "chiba":     "https://www.pref.chiba.lg.jp/kouen/toshikouen/guidemap/index.html",
    "saitama":   "https://www.pref.saitama.lg.jp/a1105/bunka_kyouiku_kennei-kouen-syoukai.html",
}


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "data" / "raw" / "_seeds"
    out.mkdir(parents=True, exist_ok=True)
    for slug, url in PAGES.items():
        r = requests.get(url, impersonate="chrome", timeout=30)
        path = out / f"{slug}.html"
        path.write_bytes(r.content)
        rel = path.relative_to(out.parent.parent.parent)
        print(f"{slug:10} {r.status_code}  {len(r.content):>7}B  -> {rel}")


if __name__ == "__main__":
    main()
