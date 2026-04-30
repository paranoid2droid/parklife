"""List the nature-themed sub-page anchors found by scan_tokyo_animals,
filtered to parks where the main page lacked an embedded species list
(so the species data must live elsewhere).
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# parks where Phase A already captured solid in-page lists; sub-pages add
# diminishing return. Skip them in the sub-page hunt.
SKIP_SLUGS = {
    "akatsuka", "kinuta", "mukojima-hyakkaen", "oizumi-chuo",
    "rinshinomori", "sakuragaoka", "shakujii", "zempukujigawa-ryokuchi",
    "zenpukuji", "oyamadaryokuchi",
}

# anchor texts that are clearly not species info
SKIP_TEXT = {
    "詳しくはこちら", "公園情報", "見どころ", "入園料", "アクセス",
    "おすすめ情報", "イベント", "ご利用にあたっての注意",
}

# url substrings that are obvious noise
SKIP_HREF = ("special_biodiversity", "facility/", "modalMenu", "modalCategory",
             "category_search", "event_search", "/news/")


def keep(text: str, href: str) -> bool:
    if not text or text in SKIP_TEXT:
        return False
    if any(s in href for s in SKIP_HREF):
        return False
    if any(s in text.lower() for s in ("ログイン", "アクセス", "パンフ")):
        return False
    return True


def main() -> None:
    scan = json.loads((ROOT / "data" / "scan" / "tokyo_animal_candidates.json").read_text(encoding="utf-8"))
    out = {}
    for slug, info in scan.items():
        if slug in SKIP_SLUGS:
            continue
        hints = info.get("anchor_hints", [])
        # also keep parks with headings (they're 'animal-aware') but no useful in-page data
        kept = [h for h in hints if keep(h["text"], h["href"])]
        # dedupe by href, keep first text
        seen = set()
        uniq = []
        for h in kept:
            if h["href"] in seen:
                continue
            seen.add(h["href"])
            uniq.append(h)
        if uniq or info.get("headings"):
            out[slug] = {
                "headings": info.get("headings", []),
                "anchors": uniq,
            }

    print(f"=== Tokyo parks with potential animal sub-pages: {len(out)} ===\n")
    for slug, item in out.items():
        print(f"  --- {slug} ---")
        for h in item["headings"][:3]:
            print(f"    H: {h}")
        for a in item["anchors"][:6]:
            print(f"    A: {a['text'][:25]:<25} {a['href']}")
        print()
    out_path = ROOT / "data" / "scan" / "tokyo_subpage_targets.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
