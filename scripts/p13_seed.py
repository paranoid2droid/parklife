"""Seed new parks from 国土数値情報 P13 都市公園データ.

For each of the 4 target prefectures, download (cache) the P13 GML zip from
nlftp.mlit.go.jp, parse, filter to biodiversity-relevant types ≥5 ha, drop
parks already in the DB (within 500m of an existing park's coordinates),
and write the result to data/seeds/<prefecture>-p13.json so the existing
curated seed lists stay untouched.

Run scripts.load_seeds afterwards to insert the new park rows.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "p13"
SEED_DIR = ROOT / "data" / "seeds"

PREFS = {"tokyo": "13", "kanagawa": "14", "chiba": "12", "saitama": "11"}
URL_FMT = "https://nlftp.mlit.go.jp/ksj/gml/data/P13/P13-11/P13-11_{code}_GML.zip"
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"

NS = {
    "ksj": "http://nlftp.mlit.go.jp/ksj/schemas/ksj-app",
    "gml": "http://www.opengis.net/gml/3.2",
    "xlink": "http://www.w3.org/1999/xlink",
}

# Park-type codes (公園種別) considered biodiversity-relevant.
# 4=総合公園, 6=広域公園, 9=特殊公園, 11=都市林, 14=都市緑地
BIODIV_KDP = {"4", "6", "9", "11", "14"}
KDP_LABEL = {
    "1": "街区公園", "2": "近隣公園", "3": "地区公園", "4": "総合公園",
    "5": "運動公園", "6": "広域公園", "7": "レクリエーション都市",
    "8": "国営公園", "9": "特殊公園", "10": "緩衝緑地", "11": "都市林",
    "12": "広場公園", "13": "緑道", "14": "都市緑地",
}
MIN_AREA_M2 = 50_000  # 5 hectares
DEDUP_RADIUS_M = 500  # treat as same park as existing if within this radius


def download_zip(pref_code: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / f"P13-11_{pref_code}_GML.zip"
    if target.exists():
        return target
    url = URL_FMT.format(code=pref_code)
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(target, "wb") as f:
        f.write(r.read())
    return target


def parse_xml(zip_path: Path) -> list[dict]:
    with zipfile.ZipFile(zip_path) as z:
        xml_name = next(n for n in z.namelist()
                        if n.endswith(".xml") and not n.startswith("KS-META"))
        with z.open(xml_name) as f:
            tree = ET.parse(f)
    root = tree.getroot()
    points = {}
    for p in root.findall("gml:Point", NS):
        pid = p.get("{http://www.opengis.net/gml/3.2}id")
        pos = (p.find("gml:pos", NS).text or "").strip().split()
        if len(pos) >= 2:
            try:
                points[pid] = (float(pos[0]), float(pos[1]))
            except ValueError:
                pass
    out = []
    for pk in root.findall("ksj:Park", NS):
        loc = pk.find("ksj:loc", NS)
        ref = (loc.get("{http://www.w3.org/1999/xlink}href") or "").lstrip("#") \
            if loc is not None else ""
        latlon = points.get(ref, (None, None))
        text = lambda tag: ((pk.find(f"ksj:{tag}", NS).text or "").strip()
                            if pk.find(f"ksj:{tag}", NS) is not None else "")
        try:
            area = int(text("opa") or 0)
        except ValueError:
            area = 0
        out.append({
            "name": text("nop"),
            "kdp": text("kdp"),
            "adm": text("adm"),
            "pop": text("pop"),
            "cop": text("cop"),
            "area": area,
            "lat": latlon[0],
            "lon": latlon[1],
        })
    return out


def haversine_m(a_lat, a_lon, b_lat, b_lon) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def stable_slug(pref: str, name: str, lat: float, lon: float) -> str:
    """Stable short slug across re-runs."""
    h = hashlib.sha1(f"{pref}|{name}|{lat:.5f}|{lon:.5f}"
                     .encode("utf-8")).hexdigest()[:10]
    return f"p13-{h}"


def existing_park_coords(db_path: Path) -> list[tuple[float, float]]:
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT lat, lon FROM park WHERE lat IS NOT NULL AND lon IS NOT NULL"
        ).fetchall()
    return [(r["lat"], r["lon"]) for r in rows]


def main() -> int:
    db_path = ROOT / "data" / "parklife.db"
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    existing = existing_park_coords(db_path)
    print(f"existing parks with coords: {len(existing)}")

    grand_new = grand_overlap = grand_filtered = 0
    for pref, code in PREFS.items():
        print(f"\n=== {pref} (code {code}) ===")
        zip_path = download_zip(code)
        parks = parse_xml(zip_path)
        print(f"  total parks in P13: {len(parks)}")

        filtered = [p for p in parks
                    if p["kdp"] in BIODIV_KDP
                    and p["area"] >= MIN_AREA_M2
                    and p["lat"] is not None]
        print(f"  filtered (biodiv types, >={MIN_AREA_M2//10000}ha): {len(filtered)}")

        new_parks = []
        overlap = 0
        for p in filtered:
            if any(haversine_m(p["lat"], p["lon"], la, lo) < DEDUP_RADIUS_M
                   for la, lo in existing):
                overlap += 1
                continue
            new_parks.append(p)
        print(f"  overlap with existing (<{DEDUP_RADIUS_M}m): {overlap}")
        print(f"  new to add: {len(new_parks)}")

        out_records = []
        for p in new_parks:
            out_records.append({
                "slug": stable_slug(pref, p["name"], p["lat"], p["lon"]),
                "name_ja": p["name"],
                "municipality": p["cop"] or None,
                "operator": p["adm"] or None,
                "lat": round(p["lat"], 6),
                "lon": round(p["lon"], 6),
                "p13_kdp": KDP_LABEL.get(p["kdp"], p["kdp"]),
                "p13_area_ha": round(p["area"] / 10000, 1),
            })
        out_path = SEED_DIR / f"{pref}-p13.json"
        out_path.write_text(json.dumps({
            "prefecture": pref,
            "source": "国土数値情報 P13-11 (都市公園)",
            "parks": out_records,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  wrote {out_path} ({len(out_records)} parks)")

        grand_new += len(new_parks)
        grand_overlap += overlap
        grand_filtered += len(filtered)

    print("\n=== summary ===")
    print(f"  filtered:  {grand_filtered}")
    print(f"  overlap:   {grand_overlap}")
    print(f"  new total: {grand_new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
