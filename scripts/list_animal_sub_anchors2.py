"""Re-filter: keep only park-specific or external animal-themed links."""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent

GLOBAL_NOISE = {
    "/special/biodiversity/", "/special/top/special_biodiversity.html/",
    "/special/top/special_biodiversity.html",
}

GLOBAL_HOST_OK = {  # external domains likely to have species data
    "kankyo.metro.tokyo.lg.jp",
    "fc2.com", "blogspot.com", "blogspot.jp",
    "tokyo-zoo.net",
}


def is_park_specific(href: str, slug: str) -> bool:
    if href in GLOBAL_NOISE:
        return False
    if href.startswith("/special/"):
        return False
    if href.startswith(f"/park/{slug}/"):
        return True
    if href.startswith(("./", "../")):
        return True
    if href.startswith("/park/") and slug not in href:
        return False  # link to other parks
    p = urlparse(href)
    if p.netloc and any(d in p.netloc for d in GLOBAL_HOST_OK):
        return True
    if p.netloc and "tokyo-park" in p.netloc:
        return False
    return bool(p.netloc)  # other external links


def main() -> None:
    scan = json.loads((ROOT / "data" / "scan" / "tokyo_animal_candidates.json").read_text(encoding="utf-8"))
    out = {}
    for slug, info in scan.items():
        anchors = info.get("anchor_hints", [])
        kept: list[dict] = []
        seen = set()
        for h in anchors:
            href = h["href"]
            if href in seen:
                continue
            text = h["text"]
            if not text or text in {"詳しくはこちら", "アクセス", "イベント", "見どころ", "ご利用にあたっての注意"}:
                continue
            if not is_park_specific(href, slug):
                continue
            seen.add(href)
            kept.append({"text": text[:30], "href": href})
        if kept:
            out[slug] = kept

    out_path = ROOT / "data" / "scan" / "tokyo_subpage_targets.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== {len(out)} parks with park-specific animal sub-page hints ===\n")
    for slug, anchors in out.items():
        print(f"  --- {slug} ({len(anchors)}) ---")
        for a in anchors[:6]:
            print(f"    {a['text']:<30}  {a['href']}")
        print()


if __name__ == "__main__":
    main()
