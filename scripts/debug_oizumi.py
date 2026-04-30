"""Debug why oizumi-chuo (which has a clear bird list) yielded new=0."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KATAKANA = re.compile(r"[ァ-ヺー]{2,12}")
scan = json.loads((ROOT / "data" / "scan" / "tokyo_animal_candidates.json").read_text(encoding="utf-8"))
info = scan.get("oizumi-chuo", {})
print("=== blocks ===")
for b in info.get("blocks", []):
    print(f"\nH: {b['heading']}")
    print(f"text: {b['text'][:600]}")
    print(f"tokens: {[m.group(0) for m in KATAKANA.finditer(b['text'])][:30]}")

# also check cache
cache_path = ROOT / "data" / "cache" / "tokyo_animal_resolution.json"
if cache_path.exists():
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    print(f"\n=== cache hits for known birds ===")
    for name in ["メジロ","ヒヨドリ","シジュウカラ","コゲラ","エナガ","オナガ","ヤマガラ","キジバト","ハクセキレイ","ムクドリ","ウグイス","モズ","シメ","ツグミ","イカル","アオジ","ジョウビタキ","カワラヒワ","ツバメ"]:
        c = cache.get(name)
        if not c:
            print(f"  {name}: NOT IN CACHE")
        else:
            print(f"  {name}: found={c.get('found')} kingdom={c.get('kingdom')} sci={c.get('scientific_name')}")
