"""Generate a single self-contained HTML browser at data/export/index.html.

Layout:
  - top bar: month picker, taxon picker, free-text search
  - left ~70%: Leaflet map of all parks (markers sized by species count)
  - right ~30%: selected park detail (species photo grid)

Data is embedded as compact JS arrays so the page works opened directly
via `file://`. Total size target < 8 MB.

Compactness:
  - Species rows are 1D entries; pairs reference by index.
  - Months are stored as the existing 12-bit bitmap (0–4095) for fast bitwise
    filtering in JavaScript.
  - Photo URLs come from species.photo_url (collected by collect_photo_urls).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from opencc import OpenCC
from parklife import db

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "export" / "index.html"

# Robust Simplified Chinese -> Traditional Chinese conversion for zhT fallback.
_OPENCC_S2T = OpenCC("s2t")


def hans_to_hant(text: str) -> str:
    return _OPENCC_S2T.convert(text or "")

# User-facing observation groups. Detailed DB taxon_group values are preserved
# in exported species rows as "tg" and shown in the modal.
GROUP_ORDER = [
    ("plant",     "🌸 植物"),
    ("bird",      "🦜 鳥類"),
    ("insect",    "🐛 昆虫"),
    ("arachnid_myriapod", "🕷 クモ・多足類"),
    ("crustacean", "🦀 甲殻類"),
    ("fish",      "🐟 魚類"),
    ("herp",      "🐸 両生・爬虫類"),
    ("mammal",    "🦌 哺乳類"),
    ("mollusk",   "🐚 貝・軟体動物"),
    ("small_aquatic", "🪸 その他水生・小動物"),
    ("mushroom",  "🍄 菌類"),
    ("unclassified", "🐾 その他生き物"),
]
PREF_NAMES = {
    "tokyo":    "東京都",
    "kanagawa": "神奈川県",
    "chiba":    "千葉県",
    "saitama":  "埼玉県",
}

SOURCE_CODE_ORDER = ["official", "inat", "gbif", "ebird"]


def medium_photo_url(url: str) -> str:
    """Use medium iNaturalist renditions in embedded data for fast modal open."""
    return (url
            .replace("/large.", "/medium.")
            .replace("/small.", "/medium.")
            .replace("/square.", "/medium."))


def demo_group(taxon_group: str | None, kingdom: str | None) -> str:
    """Map DB taxonomy to user-facing demo buckets."""
    if taxon_group in {"plant", "tree", "shrub", "herb", "vine", "fern", "moss"}:
        return "plant"
    if taxon_group in {"bird", "mammal", "fish", "insect", "crustacean", "mollusk", "mushroom"}:
        return taxon_group
    if taxon_group in {"reptile", "amphibian"}:
        return "herp"
    if taxon_group in {"arachnid", "myriapod", "sea_spider", "springtail", "arthropod"}:
        return "arachnid_myriapod"
    if taxon_group in {
        "echinoderm", "cnidarian", "annelid", "flatworm",
        "nematode", "rotifer", "bryozoan", "brachiopod",
    }:
        return "small_aquatic"
    if taxon_group:
        return "unclassified"
    k = (kingdom or "").lower()
    if k == "animalia":
        return "other_animal"
    if k == "plantae":
        return "plant"
    if k == "fungi":
        return "mushroom"
    if k in {"archaea", "bacteria", "chromista", "protozoa"}:
        return ""
    return "unclassified"


def collect_data() -> dict:
    db_path = ROOT / "data" / "parklife.db"
    db.init(db_path)
    with db.connect(db_path) as conn:
        # species: id is the row PK; we pre-collect to use as a dense index
        species_rows = list(conn.execute("""
            SELECT id, scientific_name, common_name_ja, common_name_en,
                   taxon_group, kingdom, photo_url, inat_taxon_id
            FROM species
            ORDER BY id
        """))
        # popularity = how many parks list this species
        pop = dict(conn.execute("""
            SELECT species_id, COUNT(*) FROM park_species GROUP BY species_id
        """).fetchall())
        # parks
        park_rows = list(conn.execute("""
            SELECT id, slug, name_ja, prefecture, municipality, official_url,
                   lat, lon, has_parking, parking_info
            FROM park
            ORDER BY id
        """))
        # park_species pairs (deduped)
        pair_rows = list(conn.execute("""
            SELECT park_id, species_id, months_bitmap, observation_count, source_count
            FROM park_species
        """))
        source_rows = list(conn.execute("""
            SELECT o.park_id, o.species_id, o.location_hint, s.url
            FROM observation o
            LEFT JOIN source s ON s.id = o.source_id
            WHERE o.species_id IS NOT NULL
        """))
        # zh aliases (one preferred per species per variant)
        zh_rows = list(conn.execute("""
            SELECT species_id, raw_name, lang FROM species_alias
            WHERE lang IN ('zh-Hans', 'zh-Hant')
        """))
        ebird_rows = list(conn.execute("""
            SELECT species_id, raw_name FROM species_alias
            WHERE lang = 'ebird'
        """))
        photo_rows = list(conn.execute("""
            SELECT species_id, url
            FROM species_photo
            ORDER BY species_id, sort_order, id
        """))
        profile_rows = list(conn.execute("""
            SELECT species_id, lang, summary, habitat_hint, finding_tips, sources, source_urls
            FROM species_profile
        """))
    zh_hans: dict[int, str] = {}
    zh_hant: dict[int, str] = {}
    for r in zh_rows:
        if r["lang"] == "zh-Hans":
            zh_hans.setdefault(r["species_id"], r["raw_name"])
        elif r["lang"] == "zh-Hant":
            zh_hant.setdefault(r["species_id"], r["raw_name"])
    ebird_code: dict[int, str] = {}
    for r in ebird_rows:
        ebird_code.setdefault(r["species_id"], r["raw_name"])
    gallery: dict[int, list[str]] = {}
    for r in photo_rows:
        gallery.setdefault(r["species_id"], [])
        url = medium_photo_url(r["url"]) if r["url"] else ""
        if url and url not in gallery[r["species_id"]]:
            gallery[r["species_id"]].append(url)
    profiles: dict[int, dict[str, dict[str, str]]] = {}
    for r in profile_rows:
        profiles.setdefault(r["species_id"], {})[r["lang"]] = {
            "summary": r["summary"] or "",
            "habitat": r["habitat_hint"] or "",
            "tips": r["finding_tips"] or "",
            "sources": r["sources"] or "",
            "sourceUrls": r["source_urls"] or "",
        }

    # build dense indexes (DB ids may have gaps)
    pk_idx = {r["id"]: i for i, r in enumerate(park_rows)}

    species = []
    sp_idx = {}
    for r in species_rows:
        group = demo_group(r["taxon_group"], r["kingdom"])
        if not group:
            continue
        imgs = list(gallery.get(r["id"], []))
        hero_photo = medium_photo_url(r["photo_url"]) if r["photo_url"] else ""
        if hero_photo and hero_photo not in imgs:
            imgs.insert(0, hero_photo)
        sp_idx[r["id"]] = len(species)
        item = {
            "ja":   r["common_name_ja"] or "",
            "en":   r["common_name_en"] or "",
            "zh":   zh_hans.get(r["id"], ""),
            "zhT":  zh_hant.get(r["id"], "") or hans_to_hant(zh_hans.get(r["id"], "")),
            "sci":  r["scientific_name"] or "",
            "g":    group,
            "tg":   r["taxon_group"] or "",
            "k":    r["kingdom"] or "",
            "p":    r["photo_url"] or "",
            "imgs": imgs[:5],
            "tid":  r["inat_taxon_id"] or 0,
            "eb":   ebird_code.get(r["id"], ""),
            "n":    pop.get(r["id"], 0),
        }
        if r["id"] in profiles:
            item["pr"] = profiles[r["id"]]
        species.append(item)
    parks = [
        {
            "s":  r["slug"],
            "n":  r["name_ja"],
            "pf": r["prefecture"],
            "m":  r["municipality"] or "",
            "u":  r["official_url"] or "",
            "lat": r["lat"], "lon": r["lon"],
            "park": r["has_parking"],   # 1=yes, 0=no, None=unknown
            "pi":   r["parking_info"] or "",
        }
        for r in park_rows
    ]

    pair_sources: dict[tuple[int, int], set[str]] = {}
    for r in source_rows:
        codes = pair_sources.setdefault((r["park_id"], r["species_id"]), set())
        hint = (r["location_hint"] or "").lower()
        url = (r["url"] or "").lower()
        if "ebird" in hint or "ebird" in url:
            codes.add("ebird")
        elif "gbif" in hint or "gbif" in url:
            codes.add("gbif")
        elif "inat" in hint or "inaturalist" in hint or "inaturalist" in url:
            codes.add("inat")
        else:
            codes.add("official")

    pairs = []
    for r in pair_rows:
        pi = pk_idx.get(r["park_id"])
        si = sp_idx.get(r["species_id"])
        if pi is None or si is None:
            continue
        src = [
            code for code in SOURCE_CODE_ORDER
            if code in pair_sources.get((r["park_id"], r["species_id"]), set())
        ]
        pairs.append([
            pi, si,
            r["months_bitmap"] or 0,
            r["source_count"] or 1,
            src,
            r["observation_count"] or 1,
        ])

    return {
        "species": species, "parks": parks, "pairs": pairs,
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>parklife — 関東の公園で出会える生き物</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans",
       "Yu Gothic", sans-serif; color: #222; background: #fafafa; }
header { padding: 8px 12px; background: #fff; border-bottom: 1px solid #ddd;
         display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
header h1 { font-size: 16px; margin: 0; padding: 0; color: #2a6b3b; }
header label { font-size: 13px; color: #555; display: flex; align-items: center; gap: 4px; }
header select, header input { padding: 4px 8px; font-size: 13px; border-radius: 4px;
                                border: 1px solid #ccc; background: #fff; }
header input[type=search] { width: 220px; }
.stats { font-size: 12px; color: #666; margin-left: auto; }

main { display: flex; height: calc(100vh - 50px); }
#map { flex: 7; min-height: 400px; }
#side { flex: 3; min-width: 320px; max-width: 480px; overflow-y: auto;
        background: #fff; border-left: 1px solid #ddd; padding: 12px 16px; }

.placeholder { color: #888; padding: 30px 0; text-align: center; }
.park-title-row { display: flex; align-items: center; justify-content: space-between;
                  gap: 10px; margin: 4px 0 2px; }
.park-name { font-size: 18px; font-weight: 600; margin: 4px 0 2px; }
.park-title-row .park-name { margin: 0; }
.park-map-btn { display: none; border: 1px solid #c9d8cc; background: #f3faf5;
                color: #2a6b3b; border-radius: 4px; padding: 5px 8px;
                font-size: 12px; cursor: pointer; white-space: nowrap; }
.park-map-btn:hover { background: #e8f4eb; }
.park-meta { font-size: 12px; color: #666; }
.park-meta a { color: #2a6b3b; }
.species-count { margin: 8px 0; font-size: 13px; color: #444;
                 display: flex; align-items: center; justify-content: space-between;
                 gap: 8px; flex-wrap: wrap; }
.species-count .quick-actions { display: inline-flex; align-items: center; gap: 6px; }
.species-controls { position: sticky; top: 0; background: #fff; padding: 6px 0 8px;
                    margin-top: 6px; border-bottom: 1px solid #eee; z-index: 5; }
.species-controls .row { display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: center; }
.species-controls .row.sort { margin-top: 6px; font-size: 12px; color: #555; }
.quick { border: 1px solid #c9d8cc; background: #fff; color: #2a6b3b;
         border-radius: 4px; padding: 3px 7px; font-size: 11px; cursor: pointer; }
.quick:hover { background: #e8f4eb; }
.species-controls .gck { display: inline-flex; align-items: center; gap: 3px;
                         background: #f4f4f4; padding: 2px 8px; border-radius: 12px;
                         font-size: 11px; cursor: pointer; user-select: none; }
.species-controls .gck input { margin: 0 2px 0 0; }
.species-controls .gck.off { opacity: 0.45; background: #eee; }
.species-controls select { padding: 2px 6px; font-size: 12px; border-radius: 4px;
                            border: 1px solid #ccc; background: #fff; }
.group { margin-top: 14px; }
.group.hidden { display: none; }
.group-head { width: 100%; border: none; border-bottom: 1px solid #eee; background: transparent;
              padding: 3px 0 4px; margin: 0 0 6px; display: flex; align-items: center;
              gap: 6px; color: #444; font: inherit; font-size: 13px; font-weight: 600;
              text-align: left; cursor: pointer; }
.group-head:hover { color: #2a6b3b; }
.group-head .chev { width: 1.2em; color: #777; text-align: center; }
.group.collapsed .grid, .group.collapsed .legend, .group.collapsed .more-row { display: none; }
.group.collapsed .group-head { margin-bottom: 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px,1fr)); gap: 6px; }
.card { position: relative; background: #f4f4f4; border-radius: 4px; overflow: hidden;
        font-size: 11px; line-height: 1.3; }
.card .ph { position: relative; width: 100%; aspect-ratio: 1 / 1; background: #ddd no-repeat center / cover; }
.card .lab { padding: 4px 6px; min-height: 54px; display: flex; flex-direction: column; gap: 2px; }
.card .ja { font-weight: 500; color: #222; }
.card .sci { color: #666; font-style: italic; font-size: 10px; word-break: break-all; }
.card .links { margin-top: auto; display: flex; justify-content: flex-end; gap: 4px; }
.card .links a { color: #2a6b3b; border: 1px solid #c9d8cc; background: #fff;
                 border-radius: 3px; padding: 1px 4px; font-size: 10px;
                 text-decoration: none; font-style: normal; }
.card .links a:hover { background: #e8f4eb; }
.card.no-photo .ph { background: linear-gradient(135deg,#cfe7d4,#9bd1a8); }
.inspect-btn { position: absolute; right: 5px; bottom: 5px; width: 28px; height: 28px;
               border: none; background: transparent; color: #fff; display: grid;
               place-items: center; font-size: 17px; cursor: pointer; opacity: 0;
               text-shadow: 0 1px 4px rgba(0,0,0,.85);
               transform: translateY(3px); transition: opacity .15s, transform .15s, color .15s; }
.card:hover .inspect-btn, .inspect-btn:focus { opacity: 1; transform: translateY(0); }
.inspect-btn:hover { color: #e8f4eb; }

.modal.hidden { display: none; }
.modal { position: fixed; inset: 0; z-index: 2000; display: grid; place-items: center;
         padding: 20px; }
.modal-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,.42); }
.modal-panel { position: relative; width: min(760px, 100%); max-height: min(86vh, 820px);
               overflow: auto; background: #fff; border-radius: 8px;
               box-shadow: 0 16px 42px rgba(0,0,0,.24); }
.modal-close { position: absolute; top: 8px; right: 8px; width: 32px; height: 32px;
               border: 1px solid #ddd; border-radius: 50%; background: rgba(255,255,255,.92);
               cursor: pointer; font-size: 20px; line-height: 1; z-index: 2; }
.modal-photo-wrap { position: relative; width: 100%; height: clamp(300px, 54vh, 560px);
                    background: #111; overflow: hidden; display: flex;
                    align-items: center; justify-content: center; }
.modal-photo { display: block; width: 100%; height: 100%; object-fit: contain; background: #111; }
.modal-photo.no-photo { background: linear-gradient(135deg,#cfe7d4,#9bd1a8); }
.photo-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 36px; height: 48px;
             border: none; background: rgba(0,0,0,.36); color: #fff; font-size: 28px;
             cursor: pointer; line-height: 1; }
.photo-nav:hover { background: rgba(42,107,59,.72); }
.photo-nav.prev { left: 0; }
.photo-nav.next { right: 0; }
.photo-nav.hidden, .photo-count.hidden { display: none; }
.photo-count { position: absolute; right: 8px; bottom: 8px; padding: 2px 7px;
               border-radius: 10px; background: rgba(0,0,0,.5); color: #fff;
               font-size: 12px; }
.modal-body { padding: 14px 16px 16px; }
.modal-title { font-size: 20px; font-weight: 700; margin: 0; }
.modal-sci { margin-top: 2px; color: #666; font-size: 13px; font-style: italic; }
.difficulty { display: inline-flex; gap: 8px; align-items: center; margin-top: 10px;
              padding: 5px 9px; border-radius: 4px; background: #f3faf5; color: #2a6b3b;
              font-size: 13px; font-weight: 600; }
.modal-section { margin-top: 14px; }
.modal-section h3 { margin: 0 0 5px; font-size: 13px; color: #444; }
.modal-section p, .modal-section ul { margin: 0; color: #333; font-size: 13px; line-height: 1.55; }
.modal-section ul { padding-left: 18px; }
.modal-facts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.modal-facts span { background: #f4f4f4; border-radius: 4px; padding: 3px 7px;
                    color: #555; font-size: 12px; }

.legend { font-size: 11px; color: #666; }
.more-row { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
.more-btn { border: 1px solid #c9d8cc; background: #f3faf5; color: #2a6b3b;
            border-radius: 4px; padding: 5px 8px; font-size: 12px; cursor: pointer; }
.more-btn:hover { background: #e8f4eb; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
.bird { background: #c75; } .mammal { background: #964; } .insect { background: #698; }
.plant { background: #6a4; } .reptile { background: #983; } .amphibian { background: #6b7; }
.fish { background: #469; } .arachnid { background: #976; } .mollusk { background: #678; }
.tree { background: #361; } .shrub { background: #6c3; } .herb { background: #ad7; } .vine { background: #aa5; }

.match-list { font-size: 12px; color: #444; line-height: 1.5; }
.match-list a { color: #2a6b3b; text-decoration: none; }
.match-list a:hover { text-decoration: underline; }

.parking { font-size: 12px; margin: 6px 0 4px; padding: 3px 8px; border-radius: 3px;
           display: inline-block; cursor: help; }
.parking.yes { background: #e3f2e6; color: #2a6b3b; }
.parking.no { background: #fde7e7; color: #b03030; }
.parking.unknown { background: #f0f0f0; color: #888; }

@media (max-width: 768px) {
  header { padding: 6px 8px; gap: 6px 10px; }
  header h1 { font-size: 14px; flex-basis: 100%; }
  header label { font-size: 12px; }
  header select, header input { padding: 3px 6px; font-size: 12px; }
  header input[type=search] { width: 140px; flex: 1; }
  .stats { flex-basis: 100%; margin-left: 0; }

  main { flex-direction: column; height: auto; }
  #map { flex: none; width: 100%; height: 55vh; min-height: 0; }
  #side { flex: none; width: 100%; max-width: none; min-width: 0;
          height: 45vh; border-left: none; border-top: 1px solid #ddd;
          padding: 10px 12px; }

  /* Mobile detail mode: marker tap hides the map until the user returns. */
  body.view-list #map { display: none; }
  body.view-list #side { height: calc(100vh - 90px); }
  .park-map-btn { display: inline-flex; align-items: center; }

  .grid { grid-template-columns: repeat(auto-fill, minmax(96px,1fr)); }
  .inspect-btn { opacity: 1; transform: none; }
  .modal { padding: 10px; }
  .modal-photo-wrap { height: clamp(240px, 46vh, 430px); }
  .photo-nav { width: 32px; height: 42px; font-size: 24px; }
}
</style>
</head>
<body>
<header>
  <h1>🌿 parklife</h1>
  <label>月: <select id="m"><option value="0">全て</option>
    <option value="1">1月</option><option value="2">2月</option><option value="3">3月</option>
    <option value="4">4月</option><option value="5">5月</option><option value="6">6月</option>
    <option value="7">7月</option><option value="8">8月</option><option value="9">9月</option>
    <option value="10">10月</option><option value="11">11月</option><option value="12">12月</option>
  </select></label>
  <label>分類: <select id="g"><option value="">全て</option>__GROUP_OPTS__</select></label>
  <label>🅿️ <select id="park">
    <option value="">問わず</option>
    <option value="1">あり</option>
    <option value="0">なし</option>
    <option value="?">不明</option>
  </select></label>
  <label>情報源: <select id="src">
    <option value="">全て</option>
    <option value="official">公園公式</option>
    <option value="inat">iNaturalist</option>
    <option value="gbif">GBIF</option>
    <option value="ebird">eBird</option>
  </select></label>
  <label>🌐 <select id="lang">
    <option value="ja">日本語</option>
    <option value="en">English</option>
    <option value="zh">简体中文</option>
    <option value="zhT">繁體中文</option>
  </select></label>
  <label>検索: <input type="search" id="q" placeholder="物種名 / 学名 / 公園名" /></label>
  <span class="stats" id="stat"></span>
</header>
<main>
  <div id="map"></div>
  <aside id="side">
    <div class="placeholder">📍 地図上の公園マーカーをクリック<br/>または右上の検索ボックスを使用</div>
  </aside>
</main>
<div id="species-modal" class="modal hidden" role="dialog" aria-modal="true" aria-labelledby="modal-title">
  <div class="modal-backdrop" data-modal-close></div>
  <div class="modal-panel">
    <button class="modal-close" type="button" data-modal-close aria-label="閉じる">×</button>
    <div id="modal-content"></div>
  </div>
</div>

<script>
const DATA = __DATA__;
</script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
__SCRIPT__
</script>
</body></html>
"""

CLIENT_JS = r"""
const GROUP_LABEL = {
  ja: {
    bird: '🦜 鳥類', mammal: '🦌 哺乳類', reptile: '🦎 爬虫類',
    amphibian: '🐸 両生類', fish: '🐟 魚類', insect: '🐛 昆虫',
    crustacean: '🦀 甲殻類', arachnid: '🕷 クモ類',
    myriapod: '〰️ 多足類', mollusk: '🐚 軟体動物',
    echinoderm: '✳️ 棘皮動物', cnidarian: '🪸 刺胞動物',
    annelid: '🪱 環形動物', flatworm: '➰ 扁形動物',
    sea_spider: '🕷 ウミグモ類', springtail: '▫️ トビムシ類',
    nematode: '〰️ 線形動物', rotifer: '◌ 輪形動物',
    bryozoan: '▦ コケムシ類', brachiopod: '◖ 腕足動物',
    arthropod: '🐾 節足動物',
    other_animal: '🐾 その他動物',
    plant: '🌸 植物', mushroom: '🍄 菌類',
    unclassified: '🐾 その他生き物',
  },
  en: {
    bird: '🦜 Birds', mammal: '🦌 Mammals', reptile: '🦎 Reptiles',
    amphibian: '🐸 Amphibians', fish: '🐟 Fish', insect: '🐛 Insects',
    crustacean: '🦀 Crustaceans', arachnid: '🕷 Arachnids',
    myriapod: '〰️ Myriapods', mollusk: '🐚 Molluscs',
    echinoderm: '✳️ Echinoderms', cnidarian: '🪸 Cnidarians',
    annelid: '🪱 Annelids', flatworm: '➰ Flatworms',
    sea_spider: '🕷 Sea spiders', springtail: '▫️ Springtails',
    nematode: '〰️ Nematodes', rotifer: '◌ Rotifers',
    bryozoan: '▦ Bryozoans', brachiopod: '◖ Brachiopods',
    arthropod: '🐾 Arthropods',
    other_animal: '🐾 Other animals',
    plant: '🌸 Plants', mushroom: '🍄 Fungi',
    unclassified: '🐾 Other life',
  },
  zh: {
    bird: '🦜 鸟类', mammal: '🦌 哺乳动物', reptile: '🦎 爬行动物',
    amphibian: '🐸 两栖动物', fish: '🐟 鱼类', insect: '🐛 昆虫',
    crustacean: '🦀 甲壳类', arachnid: '🕷 蛛形纲',
    myriapod: '〰️ 多足类', mollusk: '🐚 软体动物',
    echinoderm: '✳️ 棘皮动物', cnidarian: '🪸 刺胞动物',
    annelid: '🪱 环节动物', flatworm: '➰ 扁形动物',
    sea_spider: '🕷 海蜘蛛类', springtail: '▫️ 弹尾类',
    nematode: '〰️ 线虫类', rotifer: '◌ 轮虫类',
    bryozoan: '▦ 苔藓动物', brachiopod: '◖ 腕足动物',
    arthropod: '🐾 节肢动物',
    other_animal: '🐾 其他动物',
    plant: '🌸 植物', mushroom: '🍄 菌类',
    unclassified: '🐾 其他生物',
  },
  zhT: {
    bird: '🦜 鳥類', mammal: '🦌 哺乳動物', reptile: '🦎 爬蟲動物',
    amphibian: '🐸 兩棲動物', fish: '🐟 魚類', insect: '🐛 昆蟲',
    crustacean: '🦀 甲殼類', arachnid: '🕷 蛛形綱',
    myriapod: '〰️ 多足類', mollusk: '🐚 軟體動物',
    echinoderm: '✳️ 棘皮動物', cnidarian: '🪸 刺胞動物',
    annelid: '🪱 環節動物', flatworm: '➰ 扁形動物',
    sea_spider: '🕷 海蜘蛛類', springtail: '▫️ 彈尾類',
    nematode: '〰️ 線蟲類', rotifer: '◌ 輪蟲類',
    bryozoan: '▦ 苔蘚動物', brachiopod: '◖ 腕足動物',
    arthropod: '🐾 節肢動物',
    other_animal: '🐾 其他動物',
    plant: '🌸 植物', mushroom: '🍄 菌類',
    unclassified: '🐾 其他生物',
  },
};

const OBS_GROUP_LABEL = {
  ja: {
    plant: '🌸 植物', bird: '🦜 鳥類', insect: '🐛 昆虫',
    arachnid_myriapod: '🕷 クモ・多足類', crustacean: '🦀 甲殻類',
    fish: '🐟 魚類', herp: '🐸 両生・爬虫類', mammal: '🦌 哺乳類',
    mollusk: '🐚 貝・軟体動物', small_aquatic: '🪸 その他水生・小動物',
    mushroom: '🍄 菌類', unclassified: '🐾 その他生き物',
  },
  en: {
    plant: '🌸 Plants', bird: '🦜 Birds', insect: '🐛 Insects',
    arachnid_myriapod: '🕷 Spiders & myriapods', crustacean: '🦀 Crustaceans',
    fish: '🐟 Fish', herp: '🐸 Amphibians & reptiles', mammal: '🦌 Mammals',
    mollusk: '🐚 Shells & molluscs', small_aquatic: '🪸 Other aquatic small animals',
    mushroom: '🍄 Fungi', unclassified: '🐾 Other life',
  },
  zh: {
    plant: '🌸 植物', bird: '🦜 鸟类', insect: '🐛 昆虫',
    arachnid_myriapod: '🕷 蜘蛛与多足类', crustacean: '🦀 甲壳类',
    fish: '🐟 鱼类', herp: '🐸 两栖与爬行动物', mammal: '🦌 哺乳动物',
    mollusk: '🐚 贝类与软体动物', small_aquatic: '🪸 其他水生小动物',
    mushroom: '🍄 菌类', unclassified: '🐾 其他生物',
  },
  zhT: {
    plant: '🌸 植物', bird: '🦜 鳥類', insect: '🐛 昆蟲',
    arachnid_myriapod: '🕷 蜘蛛與多足類', crustacean: '🦀 甲殼類',
    fish: '🐟 魚類', herp: '🐸 兩棲與爬蟲動物', mammal: '🦌 哺乳動物',
    mollusk: '🐚 貝類與軟體動物', small_aquatic: '🪸 其他水生小動物',
    mushroom: '🍄 菌類', unclassified: '🐾 其他生物',
  },
};

const TAXON_GROUP_LABEL = {
  ja: {
    bird: '鳥類', mammal: '哺乳類', reptile: '爬虫類', amphibian: '両生類',
    fish: '魚類', insect: '昆虫', crustacean: '甲殻類', arachnid: 'クモ類',
    myriapod: '多足類', mollusk: '軟体動物', echinoderm: '棘皮動物',
    cnidarian: '刺胞動物', annelid: '環形動物', flatworm: '扁形動物',
    sea_spider: 'ウミグモ類', springtail: 'トビムシ類', nematode: '線形動物',
    rotifer: '輪形動物', bryozoan: 'コケムシ類', brachiopod: '腕足動物',
    arthropod: '節足動物', plant: '植物', tree: '樹木', shrub: '低木',
    herb: '草本', vine: 'つる植物', fern: 'シダ植物', moss: 'コケ植物',
    mushroom: '菌類',
  },
  en: {
    bird: 'Birds', mammal: 'Mammals', reptile: 'Reptiles', amphibian: 'Amphibians',
    fish: 'Fish', insect: 'Insects', crustacean: 'Crustaceans', arachnid: 'Arachnids',
    myriapod: 'Myriapods', mollusk: 'Molluscs', echinoderm: 'Echinoderms',
    cnidarian: 'Cnidarians', annelid: 'Annelids', flatworm: 'Flatworms',
    sea_spider: 'Sea spiders', springtail: 'Springtails', nematode: 'Nematodes',
    rotifer: 'Rotifers', bryozoan: 'Bryozoans', brachiopod: 'Brachiopods',
    arthropod: 'Arthropods', plant: 'Plants', tree: 'Trees', shrub: 'Shrubs',
    herb: 'Herbs', vine: 'Vines', fern: 'Ferns', moss: 'Mosses',
    mushroom: 'Fungi',
  },
  zh: {
    bird: '鸟类', mammal: '哺乳动物', reptile: '爬行动物', amphibian: '两栖动物',
    fish: '鱼类', insect: '昆虫', crustacean: '甲壳类', arachnid: '蛛形类',
    myriapod: '多足类', mollusk: '软体动物', echinoderm: '棘皮动物',
    cnidarian: '刺胞动物', annelid: '环节动物', flatworm: '扁形动物',
    sea_spider: '海蜘蛛类', springtail: '弹尾类', nematode: '线虫类',
    rotifer: '轮虫类', bryozoan: '苔藓动物', brachiopod: '腕足动物',
    arthropod: '节肢动物', plant: '植物', tree: '树木', shrub: '灌木',
    herb: '草本', vine: '藤本', fern: '蕨类', moss: '苔藓植物',
    mushroom: '菌类',
  },
  zhT: {
    bird: '鳥類', mammal: '哺乳動物', reptile: '爬蟲動物', amphibian: '兩棲動物',
    fish: '魚類', insect: '昆蟲', crustacean: '甲殼類', arachnid: '蛛形類',
    myriapod: '多足類', mollusk: '軟體動物', echinoderm: '棘皮動物',
    cnidarian: '刺胞動物', annelid: '環節動物', flatworm: '扁形動物',
    sea_spider: '海蜘蛛類', springtail: '彈尾類', nematode: '線蟲類',
    rotifer: '輪蟲類', bryozoan: '苔蘚動物', brachiopod: '腕足動物',
    arthropod: '節肢動物', plant: '植物', tree: '樹木', shrub: '灌木',
    herb: '草本', vine: '藤本', fern: '蕨類', moss: '苔蘚植物',
    mushroom: '菌類',
  },
};

const PARKING_LABELS = {
  ja: { yes: '🅿️ 駐車場あり', no: '🚫 駐車場なし', unknown: '🅿️ 駐車場情報なし', count: n => `${n} 種が条件に合致`, none: '表示する分類を選択してください', sortLabel: '並び順', sortFreq: '出現公園数（多→少）', sortName: '名称', sortSci: '学名（A→Z）', selectAll: '全選択', selectNone: '全解除', overflow: n => `…他 ${n} 種`, showMore: n => `さらに ${n} 種を表示`, showAll: n => `残り ${n} 種をすべて表示`, official: '公式 ↗', showMap: '🗺 地図', placeholder: '📍 地図上の公園マーカーをクリック<br/>または右上の検索ボックスを使用' },
  en: { yes: '🅿️ Parking available', no: '🚫 No parking', unknown: '🅿️ Parking unknown', count: n => `${n} species matched`, none: 'Choose a group to show species', sortLabel: 'Sort', sortFreq: 'Park count (high→low)', sortName: 'Name', sortSci: 'Scientific name (A→Z)', selectAll: 'Select all', selectNone: 'Select none', overflow: n => `…and ${n} more`, showMore: n => `Show ${n} more`, showAll: n => `Show all ${n} remaining`, official: 'Official ↗', showMap: '🗺 Map', placeholder: '📍 Click a park marker on the map<br/>or use the search box' },
  zh: { yes: '🅿️ 有停车场', no: '🚫 无停车场', unknown: '🅿️ 停车场信息未知', count: n => `共 ${n} 种符合条件`, none: '请选择分类后显示物种', sortLabel: '排序', sortFreq: '公园数（多→少）', sortName: '名称', sortSci: '学名（A→Z）', selectAll: '全选', selectNone: '全不选', overflow: n => `…还有 ${n} 种`, showMore: n => `再显示 ${n} 种`, showAll: n => `显示剩余全部 ${n} 种`, official: '官网 ↗', showMap: '🗺 地图', placeholder: '📍 点击地图上的公园标记<br/>或使用右上角搜索框' },
  zhT: { yes: '🅿️ 有停車場', no: '🚫 無停車場', unknown: '🅿️ 停車場資訊未知', count: n => `共 ${n} 種符合條件`, none: '請選擇分類後顯示物種', sortLabel: '排序', sortFreq: '公園數（多→少）', sortName: '名稱', sortSci: '學名（A→Z）', selectAll: '全選', selectNone: '全不選', overflow: n => `…還有 ${n} 種`, showMore: n => `再顯示 ${n} 種`, showAll: n => `顯示剩餘全部 ${n} 種`, official: '官網 ↗', showMap: '🗺 地圖', placeholder: '📍 點擊地圖上的公園標記<br/>或使用右上角搜尋框' },
};

const DETAIL_LABELS = {
  ja: {
    inspect: '観察ガイドを開く', difficulty: '観察難度', guide: '見つけ方',
    profile: 'この生き物について', habitat: 'いそうな場所',
    fieldTips: '探し方', profileSources: 'プロフィール参考',
    parkClue: 'この公園での手がかり', timing: '観察時期の目安', source: '記録ソース',
    evidence: 'この公園での記録数',
    taxonomy: '詳しい分類',
    spread: '記録公園数', unknownSeason: '通年または不明',
    months: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
    levels: ['とても見つけやすい','見つけやすい','少し探す','条件が合うと見つかる','かなり難しい'],
    sources: { official: '公園公式', inat: 'iNaturalist', gbif: 'GBIF', ebird: 'eBird' },
  },
  en: {
    inspect: 'Open field guide', difficulty: 'Finding difficulty', guide: 'How to find it',
    profile: 'About this species', habitat: 'Likely places',
    fieldTips: 'How to find it', profileSources: 'Profile references',
    parkClue: 'Clues in this park', timing: 'Observation timing', source: 'Record sources',
    evidence: 'Records in this park',
    taxonomy: 'Detailed group',
    spread: 'Parks recorded', unknownSeason: 'Year-round or unknown',
    months: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
    levels: ['Very easy','Easy','Takes some searching','Seasonal or habitat-dependent','Hard to find'],
    sources: { official: 'Official park data', inat: 'iNaturalist', gbif: 'GBIF', ebird: 'eBird' },
  },
  zh: {
    inspect: '打开观察指南', difficulty: '观察难度', guide: '寻找方法',
    profile: '关于这个物种', habitat: '可能出现的地方',
    fieldTips: '寻找方法', profileSources: '简介参考',
    parkClue: '这个公园里的线索', timing: '观察时机参考', source: '记录来源',
    evidence: '这个公园的记录数',
    taxonomy: '详细分类',
    spread: '有记录的公园数', unknownSeason: '全年或未知',
    months: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
    levels: ['很容易看到','比较容易','需要稍微寻找','看季节和环境','比较难看到'],
    sources: { official: '公园官网', inat: 'iNaturalist', gbif: 'GBIF', ebird: 'eBird' },
  },
  zhT: {
    inspect: '打開觀察指南', difficulty: '觀察難度', guide: '尋找方法',
    profile: '關於這個物種', habitat: '可能出現的地方',
    fieldTips: '尋找方法', profileSources: '簡介參考',
    parkClue: '這個公園裡的線索', timing: '觀察時機參考', source: '記錄來源',
    evidence: '這個公園的記錄數',
    taxonomy: '詳細分類',
    spread: '有記錄的公園數', unknownSeason: '全年或未知',
    months: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
    levels: ['很容易看到','比較容易','需要稍微尋找','看季節和環境','比較難看到'],
    sources: { official: '公園官網', inat: 'iNaturalist', gbif: 'GBIF', ebird: 'eBird' },
  },
};

const GUIDE_TEMPLATES = {
  ja: {
    bird: '水辺、樹冠、草地の縁をゆっくり見てください。鳥は朝夕に動きが出やすく、先に声や動きを見つけると探しやすくなります。',
    plant: '園路沿い、林縁、花壇や湿った場所を見比べてください。花や果実の時期は見つけやすく、葉の形も大事な手がかりです。',
    insect: '晴れて暖かい時間帯に、花、草地、林縁を重点的に探してください。飛んでいる姿だけでなく、葉の裏や茎も見ると見つかりやすいです。',
    arachnid: '草むら、低木、柵まわり、林縁をゆっくり見てください。網、葉の裏、地表近くが手がかりになります。',
    mushroom: '雨の後に、落ち葉、枯れ木、湿った林床を探してください。短期間だけ出ることが多いのでタイミングが重要です。',
    fish: '池や流れの浅い場所、水草の周辺、橋やデッキの上から水面を静かに観察してください。',
    amphibian: '雨上がりや夕方に、水辺、湿った草地、落ち葉の下を探すと出会いやすくなります。',
    reptile: '日当たりのよい石、草地の縁、水辺近くを静かに探してください。近づきすぎるとすぐ隠れます。',
    mammal: '早朝や夕方に、林縁、草地、足跡や食痕を探してください。姿よりも痕跡から気づくことが多いです。',
    crustacean: '水辺の石の下、干潟、池の縁、湿った落ち葉の下を静かに見てください。小さな穴や動く影が手がかりになります。',
    myriapod: '落ち葉、倒木、石の下など湿った暗い場所をそっと確認してください。観察後は元の状態に戻すのが大切です。',
    echinoderm: '海辺や磯に近い公園では、潮だまり、砂地、岩のすき間を探してください。干潮時の観察が向いています。',
    cnidarian: '海辺では潮だまりや打ち上げられた個体、水面近くを確認してください。触らず距離を取って観察します。',
    annelid: '湿った土、泥、干潟、石の下を探してください。地表の小さな盛り上がりや巣穴も手がかりです。',
    flatworm: '湿った落ち葉、石の裏、倒木の下をそっと見てください。雨上がりや湿度の高い日が狙い目です。',
    sea_spider: '磯の海藻、岩の表面、潮だまりを近くで観察してください。とても小さいので写真を拡大すると確認しやすいです。',
    springtail: '湿った落ち葉や苔の表面をよく見ると見つかります。小さいので、しゃがんでゆっくり探すのが近道です。',
    nematode: '肉眼では見つけにくいことが多く、土壌や水中の微小環境に記録が偏ります。資料リンクで確認する対象です。',
    rotifer: '池や湿った苔などの微小な水環境にいます。現地では肉眼観察より資料確認向きです。',
    bryozoan: '水中の石、杭、海藻、貝殻などに群体として付着します。水辺や磯で表面の質感を確認してください。',
    brachiopod: '磯や海底由来の記録が中心です。現地で探す場合は貝殻状の小さな個体を資料と照合してください。',
    arthropod: '石の下、落ち葉、湿った水辺、草地の縁などをゆっくり見比べてください。脚の数や体の節が手がかりです。',
    other_animal: '水辺、落ち葉、石の下、草地の縁など、小さな環境の違いをゆっくり見てください。',
    unclassified: '写真、季節、見つかった場所を手がかりに、外部リンクで特徴を確認しながら探してください。',
  },
  en: {
    bird: 'Scan water edges, tree canopies, and meadow edges slowly. Birds are often more active in the morning and evening; sound and movement are the first clues.',
    plant: 'Compare path edges, woodland edges, flower beds, and damp spots. Flowers or fruit make it easier, but leaf shape is often the key clue.',
    insect: 'Look on warm sunny hours around flowers, grassland, and woodland edges. Check leaf undersides and stems, not only flying individuals.',
    arachnid: 'Search grass, shrubs, fences, and woodland edges slowly. Webs, leaf undersides, and low vegetation are useful clues.',
    mushroom: 'After rain, check leaf litter, dead wood, and damp woodland floor. Many fruiting bodies appear only briefly, so timing matters.',
    fish: 'Watch shallow pond or stream edges, aquatic plants, and quiet water from bridges or decks.',
    amphibian: 'After rain or near dusk, check watersides, damp grass, and leaf litter.',
    reptile: 'Search sunny stones, grass edges, and watersides quietly. They often hide quickly if approached.',
    mammal: 'Early morning or evening is best. Check woodland edges, grassland, tracks, and feeding signs.',
    crustacean: 'Check under stones near water, tidal flats, pond edges, and damp leaf litter. Small burrows or moving shadows are useful clues.',
    myriapod: 'Gently check damp dark places such as leaf litter, fallen logs, and stones. Put the habitat back as it was after observing.',
    echinoderm: 'Near coastal parks, search tide pools, sandy patches, and rock crevices. Low tide is usually best.',
    cnidarian: 'Near the sea, scan tide pools, stranded individuals, and the water surface. Observe without touching.',
    annelid: 'Look in damp soil, mud, tidal flats, and under stones. Small mounds or burrows can be clues.',
    flatworm: 'Gently check damp leaf litter, undersides of stones, and fallen logs. Humid days after rain are best.',
    sea_spider: 'Inspect seaweed, rock surfaces, and tide pools closely. They are tiny, so zoomed photos help.',
    springtail: 'Look closely at damp leaf litter and moss. Crouching down and scanning slowly helps with these tiny animals.',
    nematode: 'Often too small for field viewing; records usually come from soil or aquatic microhabitats. Use reference links for confirmation.',
    rotifer: 'Found in tiny water habitats such as ponds and wet moss. In the field they are usually a reference-check target, not a naked-eye find.',
    bryozoan: 'Look for colonies attached to submerged stones, posts, seaweed, or shells; check textures on water-edge surfaces.',
    brachiopod: 'Mostly coastal or seafloor-derived records. Compare small shell-like animals with reference images.',
    arthropod: 'Compare stones, leaf litter, damp water edges, and grass margins slowly. Body segments and leg count are useful clues.',
    other_animal: 'Look slowly across small habitat changes such as water edges, leaf litter, under stones, and grass margins.',
    unclassified: 'Use the photo, season, and location as clues, then confirm details through the external reference links.',
  },
  zh: {
    bird: '慢慢观察水边、树冠和草地边缘。鸟类在清晨和傍晚更活跃，声音和移动往往是最先出现的线索。',
    plant: '比较园路边、林缘、花坛和潮湿处。开花或结果时最容易确认，叶形也是重要线索。',
    insect: '晴朗温暖的时段，重点看花附近、草地和林缘。除了飞行中的个体，也要看叶背和茎上。',
    arachnid: '慢慢查看草丛、灌木、围栏附近和林缘。蛛网、叶背和靠近地面的植被都是线索。',
    mushroom: '雨后留意落叶层、枯木和潮湿林地。很多菌类出现时间很短，时机很重要。',
    fish: '在池塘、溪流浅水处、水草周围，或桥和平台上安静观察水面。',
    amphibian: '雨后或傍晚，在水边、潮湿草地和落叶层附近更容易遇到。',
    reptile: '安静查看向阳的石头、草地边缘和水边附近。靠太近时它们通常会很快躲开。',
    mammal: '清晨或傍晚更适合。可以留意林缘、草地、足迹和取食痕迹。',
    crustacean: '安静查看水边石头下、潮滩、池塘边缘和潮湿落叶层。小洞和移动的影子常是线索。',
    myriapod: '轻轻查看落叶层、倒木和石头下等潮湿阴暗处。观察后请把环境恢复原状。',
    echinoderm: '靠海的公园可在潮池、沙地和岩缝中寻找，退潮时更适合观察。',
    cnidarian: '海边可看潮池、被冲上岸的个体和近水面处。不要触摸，保持距离观察。',
    annelid: '查看潮湿土壤、泥地、潮滩和石头下。小土堆或洞口也是线索。',
    flatworm: '轻轻查看潮湿落叶、石头背面和倒木下。雨后或湿度高时更容易遇到。',
    sea_spider: '仔细看潮池、海藻和岩石表面。它们通常很小，放大照片更容易确认。',
    springtail: '在潮湿落叶和苔藓表面仔细看。个体很小，蹲下来慢慢扫视会更有效。',
    nematode: '多数很难用肉眼寻找，记录常来自土壤或水中的微小环境，更适合通过资料链接确认。',
    rotifer: '常见于池塘、湿苔藓等微小水环境，现场多半不是肉眼观察对象。',
    bryozoan: '常以群体附着在水下石头、木桩、海藻或贝壳上，可观察水边表面的质感。',
    brachiopod: '多为海岸或海底相关记录。现场寻找时可用贝壳状小型个体与资料图对照。',
    arthropod: '慢慢比较石头下、落叶层、水边潮湿处和草地边缘。身体分节和足的数量是线索。',
    other_animal: '慢慢观察水边、落叶层、石头下和草地边缘等小环境差异。',
    unclassified: '先用照片、季节和发现地点作为线索，再通过外部链接确认特征。',
  },
  zhT: {
    bird: '慢慢觀察水邊、樹冠和草地邊緣。鳥類在清晨和傍晚更活躍，聲音和移動往往是最先出現的線索。',
    plant: '比較園路邊、林緣、花壇和潮濕處。開花或結果時最容易確認，葉形也是重要線索。',
    insect: '晴朗溫暖的時段，重點看花附近、草地和林緣。除了飛行中的個體，也要看葉背和莖上。',
    arachnid: '慢慢查看草叢、灌木、圍欄附近和林緣。蛛網、葉背和靠近地面的植被都是線索。',
    mushroom: '雨後留意落葉層、枯木和潮濕林地。很多菌類出現時間很短，時機很重要。',
    fish: '在池塘、溪流淺水處、水草周圍，或橋和平台上安靜觀察水面。',
    amphibian: '雨後或傍晚，在水邊、潮濕草地和落葉層附近更容易遇到。',
    reptile: '安靜查看向陽的石頭、草地邊緣和水邊附近。靠太近時牠們通常會很快躲開。',
    mammal: '清晨或傍晚更適合。可以留意林緣、草地、足跡和取食痕跡。',
    crustacean: '安靜查看水邊石頭下、潮灘、池塘邊緣和潮濕落葉層。小洞和移動的影子常是線索。',
    myriapod: '輕輕查看落葉層、倒木和石頭下等潮濕陰暗處。觀察後請把環境恢復原狀。',
    echinoderm: '靠海的公園可在潮池、沙地和岩縫中尋找，退潮時更適合觀察。',
    cnidarian: '海邊可看潮池、被沖上岸的個體和近水面處。不要觸摸，保持距離觀察。',
    annelid: '查看潮濕土壤、泥地、潮灘和石頭下。小土堆或洞口也是線索。',
    flatworm: '輕輕查看潮濕落葉、石頭背面和倒木下。雨後或濕度高時更容易遇到。',
    sea_spider: '仔細看潮池、海藻和岩石表面。牠們通常很小，放大照片更容易確認。',
    springtail: '在潮濕落葉和苔蘚表面仔細看。個體很小，蹲下來慢慢掃視會更有效。',
    nematode: '多數很難用肉眼尋找，記錄常來自土壤或水中的微小環境，更適合透過資料連結確認。',
    rotifer: '常見於池塘、濕苔蘚等微小水環境，現場多半不是肉眼觀察對象。',
    bryozoan: '常以群體附著在水下石頭、木樁、海藻或貝殼上，可觀察水邊表面的質感。',
    brachiopod: '多為海岸或海底相關記錄。現場尋找時可用貝殼狀小型個體與資料圖對照。',
    arthropod: '慢慢比較石頭下、落葉層、水邊潮濕處和草地邊緣。身體分節和足的數量是線索。',
    other_animal: '慢慢觀察水邊、落葉層、石頭下和草地邊緣等小環境差異。',
    unclassified: '先用照片、季節和發現地點作為線索，再透過外部連結確認特徵。',
  },
};

// Active UI language (persistent)
const LANG_KEY = 'parklife.lang';
let displayLang = localStorage.getItem(LANG_KEY) || 'ja';
const LOCALE_FOR_LANG = { ja: 'ja', en: 'en', zh: 'zh-Hans', zhT: 'zh-Hant' };

// Best-effort name in active language with fallback chain
function displayName(sp) {
  return sp[displayLang] || sp.ja || sp.en || sp.sci || '?';
}
function groupLabel(g) {
  return (OBS_GROUP_LABEL[displayLang] || OBS_GROUP_LABEL.ja)[g] || g;
}
function detailGroupLabel(sp) {
  const key = sp.tg || sp.g || '';
  return (TAXON_GROUP_LABEL[displayLang] || TAXON_GROUP_LABEL.ja)[key]
      || (OBS_GROUP_LABEL[displayLang] || OBS_GROUP_LABEL.ja)[sp.g]
      || key
      || '-';
}
function labels() { return PARKING_LABELS[displayLang] || PARKING_LABELS.ja; }
function detailLabels() { return DETAIL_LABELS[displayLang] || DETAIL_LABELS.ja; }

// Build per-park indices (which species are at each park, with months)
const parkSpecies = DATA.parks.map(()=> []);
for (const [pi, si, mb, sc, src, oc] of DATA.pairs) {
  parkSpecies[pi].push({si, mb, sc, src: src || [], oc: oc || 1});
}

const map = L.map('map', { zoomControl: true }).setView([35.65, 139.7], 9);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 18, attribution: '© OpenStreetMap'
}).addTo(map);

const markerLayer = L.layerGroup().addTo(map);
const sideEl = document.getElementById('side');
const statEl = document.getElementById('stat');
let selectedParkIdx = null;
let userSelectedPark = false;
const DEFAULT_RECOMMEND_POINT = { lat: 35.681236, lon: 139.767125 }; // Tokyo Station
const MAX_LOCATION_RECOMMEND_KM = 80;

// Per-park species panel: persistent group-checkbox + sort state
const SELECTED_GROUPS_KEY = 'parklife.selectedGroups.v2';
const SORT_KEY = 'parklife.speciesSort';
const EXPANDED_GROUPS_KEY = 'parklife.expandedGroups.v1';
const GROUP_LIMIT_STEP = 80;
let selectedGroups = new Set();
try { selectedGroups = new Set(JSON.parse(localStorage.getItem(SELECTED_GROUPS_KEY) || '[]')); }
catch (e) { selectedGroups = new Set(); }
let sortMode = localStorage.getItem(SORT_KEY) || 'freq'; // 'freq' | 'name' | 'sci'
if (sortMode === 'ja') sortMode = 'name'; // migration from old key
let expandedGroups = new Set();
try { expandedGroups = new Set(JSON.parse(localStorage.getItem(EXPANDED_GROUPS_KEY) || '[]')); }
catch (e) { expandedGroups = new Set(); }
let expandedGroupLimits = {};
let currentModal = null;
let modalTouchStartX = null;
const largePhotoCache = new Set();

function persistSelectedGroups() {
  try { localStorage.setItem(SELECTED_GROUPS_KEY, JSON.stringify([...selectedGroups])); } catch(e) {}
}
function persistSort() { try { localStorage.setItem(SORT_KEY, sortMode); } catch(e) {} }
function persistExpanded() {
  try { localStorage.setItem(EXPANDED_GROUPS_KEY, JSON.stringify([...expandedGroups])); } catch(e) {}
}
function groupLimitKey(pi, g) { return `${pi}:${g}`; }
function visibleLimitFor(pi, g) {
  return expandedGroupLimits[groupLimitKey(pi, g)] || GROUP_LIMIT_STEP;
}
function setVisibleLimit(pi, g, n) {
  expandedGroupLimits[groupLimitKey(pi, g)] = n;
}

function wikiSearchUrl(sp) {
  const host = displayLang === 'en' ? 'en.wikipedia.org'
             : (displayLang === 'zh' || displayLang === 'zhT') ? 'zh.wikipedia.org'
             : 'ja.wikipedia.org';
  const q = displayName(sp) || sp.sci || '';
  return `https://${host}/wiki/Special:Search?search=${encodeURIComponent(q)}`;
}

function ebirdSpeciesUrl(sp) {
  const siteLanguage = displayLang === 'ja' ? 'ja'
                     : displayLang === 'zh' ? 'zh_CN'
                     : displayLang === 'zhT' ? 'zh_TW'
                     : '';
  const base = `https://ebird.org/species/${encodeURIComponent(sp.eb)}`;
  return siteLanguage ? `${base}?siteLanguage=${siteLanguage}` : base;
}

function inatTaxonUrl(sp) {
  const locale = displayLang === 'ja' ? 'ja'
               : (displayLang === 'zh' || displayLang === 'zhT') ? 'zh'
               : 'en';
  return `https://www.inaturalist.org/taxa/${sp.tid}?locale=${locale}`;
}

function monthsText(bitmap) {
  const D = detailLabels();
  if (!bitmap) return D.unknownSeason;
  const months = [];
  for (let i = 0; i < 12; i++) {
    if (bitmap & (1 << i)) months.push(D.months[i]);
  }
  return months.length ? months.join(' · ') : D.unknownSeason;
}

const TIMING_OVERRIDES = {
  ja: {
    'Streptopelia orientalis': '留鳥として一年を通して観察できます。繁殖期は春から夏、採食中は地面や低い枝で見つけやすいです。',
    'Hypsipetes amaurotis': '一年を通して見られます。花や実が多い時期は木の上部に集まりやすく、声も手がかりになります。',
    'Motacilla alba': '一年を通して見られます。開けた地面や水辺では季節を問わず探せます。',
    'Parus cinereus': '一年を通して見られます。冬は混群で動くことがあり、春は声で気づきやすくなります。',
    'Zosterops japonicus': '一年を通して見られます。冬から春は花木、秋は実のなる木で探しやすいです。',
    'Passer montanus': '一年を通して見られます。繁殖期は巣材や餌を運ぶ行動も手がかりになります。',
  },
  en: {
    'Streptopelia orientalis': 'Usually observable year-round as a resident bird. Spring to summer is breeding season; feeding birds are often on the ground or low branches.',
    'Hypsipetes amaurotis': 'Usually observable year-round. Flowering and fruiting trees make it easier to find.',
    'Motacilla alba': 'Usually observable year-round around open ground and watersides.',
    'Parus cinereus': 'Usually observable year-round. Winter mixed flocks and spring calls are good clues.',
    'Zosterops japonicus': 'Usually observable year-round. Flowering trees in winter-spring and fruiting trees in autumn are useful spots.',
    'Passer montanus': 'Usually observable year-round. Nest material or food-carrying behavior can be visible in breeding season.',
  },
  zh: {
    'Streptopelia orientalis': '作为留鸟通常全年都能观察。春夏为繁殖期，觅食时常在地面或低枝上。', 'Hypsipetes amaurotis': '通常全年可见。开花、结果的树会让它更容易被发现。',
    'Motacilla alba': '通常全年可见，开阔地面和水边都适合寻找。', 'Parus cinereus': '通常全年可见。冬季混群和春季叫声都是好线索。',
    'Zosterops japonicus': '通常全年可见。冬春看花木，秋季看结果树更容易。', 'Passer montanus': '通常全年可见。繁殖期搬运巢材或食物的行为也是线索。',
  },
  zhT: {
    'Streptopelia orientalis': '作為留鳥通常全年都能觀察。春夏為繁殖期，覓食時常在地面或低枝上。', 'Hypsipetes amaurotis': '通常全年可見。開花、結果的樹會讓牠更容易被發現。',
    'Motacilla alba': '通常全年可見，開闊地面和水邊都適合尋找。', 'Parus cinereus': '通常全年可見。冬季混群和春季叫聲都是好線索。',
    'Zosterops japonicus': '通常全年可見。冬春看花木，秋季看結果樹更容易。', 'Passer montanus': '通常全年可見。繁殖期搬運巢材或食物的行為也是線索。',
  },
};

const TIMING_BY_GROUP = {
  ja: {
    bird: '種によって異なります。留鳥は通年、冬鳥は冬、夏鳥は春から夏が中心です。記録月ではなく生活史の目安として見てください。',
    plant: '花・果実・紅葉など見たい状態で時期が変わります。葉だけなら長く見られる種も多いです。',
    insect: '多くは暖かい季節、とくに春から秋の晴れた日中に見つけやすいです。',
    mushroom: '雨の後や湿度の高い時期が中心です。子実体は短期間だけ出ることがあります。',
    herp: '暖かい季節と雨上がりに活動しやすく、冬は見つけにくくなります。',
    fish: '水中では通年見られる種も多いですが、水温や繁殖期で見えやすさが変わります。',
    default: '時期は種によって異なります。ここでは記録月ではなく、分類と生活習性に基づく目安を表示しています。',
  },
  en: { default: 'Timing varies by species. This is a natural-history hint, not a list of upload or record months.' },
  zh: { default: '观察时机会因物种而异。这里显示的是生活习性参考，不是照片上传或记录月份。' },
  zhT: { default: '觀察時機會因物種而異。這裡顯示的是生活習性參考，不是照片上傳或記錄月份。' },
};

function observationTimingText(sp) {
  const lang = displayLang;
  const override = (TIMING_OVERRIDES[lang] || TIMING_OVERRIDES.ja)[sp.sci];
  if (override) return override;
  const groupHints = TIMING_BY_GROUP[lang] || TIMING_BY_GROUP.ja;
  return groupHints[sp.g] || groupHints[sp.tg] || groupHints.default || TIMING_BY_GROUP.ja.default;
}

function sourceText(pair) {
  const D = detailLabels();
  const src = pair && pair.src && pair.src.length ? pair.src : [];
  if (!src.length) return `${pair ? pair.sc || 1 : 1}`;
  return src.map(code => D.sources[code] || code).join(' · ');
}

function difficultyLevel(sp, pair) {
  const n = sp.n || 0;
  const oc = pair && pair.oc ? pair.oc : 1;
  const sc = pair && pair.sc ? pair.sc : 1;
  const src = pair && pair.src ? pair.src : [];
  let level = 4;

  if (oc >= 5 || sc >= 4) level = 1;
  else if (oc >= 3 || sc >= 3) level = 2;
  else if (oc >= 2 || sc >= 2) level = 3;

  if (src.includes('official')) level -= 1;
  if (src.length >= 2) level -= 1;
  if (src.length === 1 && src[0] === 'gbif') level += 1;
  if (n >= 100) level -= 1;
  else if (n <= 3) level += 1;

  const f = currentFilter();
  if (f.monthBit && pair && pair.mb && (pair.mb & f.monthBit)) level -= 1;

  if (sp.g === 'plant' && n >= 3) level -= 1;
  if (sp.g === 'mushroom' || sp.g === 'herp' || sp.g === 'small_aquatic') level += 1;
  if (sp.g === 'mammal') level += 1;
  return Math.max(1, Math.min(5, level));
}

function difficultyHtml(sp, pair) {
  const D = detailLabels();
  const level = difficultyLevel(sp, pair);
  return `${'★'.repeat(level)}${'☆'.repeat(5 - level)} ${D.levels[level - 1]}`;
}

function guideText(sp) {
  const templates = GUIDE_TEMPLATES[displayLang] || GUIDE_TEMPLATES.ja;
  return templates[sp.g] || templates[sp.tg] || templates.unclassified;
}

function profileFor(sp) {
  if (!sp.pr) return null;
  return sp.pr[displayLang] || sp.pr.ja || sp.pr.en || null;
}

function escapeHtml(text) {
  return String(text || '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

function profileSourceText(profile) {
  if (!profile || !profile.sources) return '';
  try {
    const parsed = JSON.parse(profile.sources);
    if (Array.isArray(parsed)) return parsed.join(' · ');
  } catch (e) {}
  return profile.sources;
}

function profileSourceLinks(profile) {
  if (!profile || !profile.sourceUrls) return '';
  let parsed = [];
  try {
    parsed = JSON.parse(profile.sourceUrls);
  } catch (e) {
    return '';
  }
  if (!Array.isArray(parsed) || !parsed.length) return '';
  return parsed
    .filter(item => item && item.url)
    .map(item => `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.label || item.url)}</a>`)
    .join(' · ');
}

function profileSectionHtml(sp) {
  const D = detailLabels();
  const profile = profileFor(sp);
  if (!profile) {
    return `<div class="modal-section"><h3>${D.guide}</h3><p>${escapeHtml(guideText(sp))}</p></div>`;
  }
  const source = profileSourceText(profile);
  const sourceLinks = profileSourceLinks(profile);
  let html = `<div class="modal-section"><h3>${D.profile}</h3><p>${escapeHtml(profile.summary)}</p></div>`;
  if (profile.habitat) {
    html += `<div class="modal-section"><h3>${D.habitat}</h3><p>${escapeHtml(profile.habitat)}</p></div>`;
  }
  if (profile.tips) {
    html += `<div class="modal-section"><h3>${D.fieldTips}</h3><p>${escapeHtml(profile.tips)}</p></div>`;
  }
  if (source) {
    html += `<div class="modal-section subtle"><h3>${D.profileSources}</h3><p>${escapeHtml(source)}${sourceLinks ? `<br>${sourceLinks}` : ''}</p></div>`;
  }
  return html;
}

function speciesPhotos(sp) {
  return sp.imgs && sp.imgs.length ? sp.imgs : (sp.p ? [sp.p] : []);
}

function largePhotoUrl(url) {
  return (url || '').replace('/medium.', '/large.').replace('/small.', '/large.').replace('/square.', '/large.');
}

function preloadLargePhoto(url) {
  const large = largePhotoUrl(url);
  if (!large || largePhotoCache.has(large)) return;
  const img = new Image();
  img.onload = () => largePhotoCache.add(large);
  img.src = large;
}

function speciesCardHtml(sp, pair) {
  const photo = sp.p ? `style="background-image:url('${sp.p}')"` : '';
  const cls = sp.p ? 'card' : 'card no-photo';
  const name = displayName(sp);
  const sci = sp.sci ? `<div class="sci">${sp.sci}</div>` : '';
  const inspect = detailLabels().inspect;
  const wiki = `<a href="${wikiSearchUrl(sp)}" target="_blank" rel="noopener" title="Wikipedia">Wiki</a>`;
  const inat = sp.tid ? `<a href="${inatTaxonUrl(sp)}" target="_blank" rel="noopener" title="iNaturalist">iNat</a>` : '';
  const ebird = sp.eb ? `<a href="${ebirdSpeciesUrl(sp)}" target="_blank" rel="noopener" title="eBird">eBird</a>` : '';
  const links = `<div class="links">${wiki}${inat}${ebird}</div>`;
  return `<div class="${cls}"><div class="ph" ${photo}>` +
         `<button class="inspect-btn" type="button" data-open-species="${pair.si}" aria-label="${inspect}" title="${inspect}">🔍</button>` +
         `</div>` +
         `<div class="lab"><div class="ja">${name}</div>${sci}${links}</div></div>`;
}

function openSpeciesModal(si) {
  const sp = DATA.species[si];
  if (!sp) return;
  const pair = selectedParkIdx == null ? null : parkSpecies[selectedParkIdx].find(p => p.si === si);
  const park = selectedParkIdx == null ? null : DATA.parks[selectedParkIdx];
  const D = detailLabels();
  const photos = speciesPhotos(sp);
  currentModal = { si, photoIdx: 0, photos };
  const hasGallery = photos.length > 1;
  const photoEl = photos.length
    ? `<img id="modal-photo" class="modal-photo" src="${photos[0]}" alt="${displayName(sp)}" />`
    : `<div id="modal-photo" class="modal-photo no-photo"></div>`;
  const sci = sp.sci ? `<div class="modal-sci">${sp.sci}</div>` : '';
  const facts = [
    `${D.taxonomy}: ${detailGroupLabel(sp)}`,
    `${D.evidence}: ${pair ? pair.oc || 1 : 1}`,
    `${D.spread}: ${sp.n || 0}`,
    `${D.source}: ${sourceText(pair)}`,
  ];
  const content = document.getElementById('modal-content');
  content.innerHTML =
    `<div class="modal-photo-wrap" data-gallery-touch>` +
      photoEl +
      `<button class="photo-nav prev${hasGallery ? '' : ' hidden'}" type="button" data-photo-prev aria-label="Previous photo">‹</button>` +
      `<button class="photo-nav next${hasGallery ? '' : ' hidden'}" type="button" data-photo-next aria-label="Next photo">›</button>` +
      `<div id="photo-count" class="photo-count${hasGallery ? '' : ' hidden'}">1 / ${photos.length}</div>` +
    `</div>` +
    `<div class="modal-body">` +
      `<h2 class="modal-title" id="modal-title">${displayName(sp)}</h2>${sci}` +
      `<div class="difficulty">${D.difficulty}: ${difficultyHtml(sp, pair)}</div>` +
      `<div class="modal-facts">${facts.map(f => `<span>${f}</span>`).join('')}</div>` +
      `<div class="modal-section"><h3>${D.timing}</h3><p>${escapeHtml(observationTimingText(sp))}</p></div>` +
      profileSectionHtml(sp) +
      `<div class="modal-section"><h3>${D.parkClue}${park ? ` · ${park.n}` : ''}</h3>` +
      `<p>${D.evidence}: ${pair ? pair.oc || 1 : 1} / ${D.source}: ${sourceText(pair)}</p></div>` +
    `</div>`;
  document.getElementById('species-modal').classList.remove('hidden');
  wireGalleryControls();
  upgradeModalPhoto();
  if (photos.length > 1) preloadLargePhoto(photos[1]);
}

function closeSpeciesModal() {
  document.getElementById('species-modal').classList.add('hidden');
  currentModal = null;
  modalTouchStartX = null;
}

function renderModalPhoto() {
  if (!currentModal || !currentModal.photos.length) return;
  const photoEl = document.getElementById('modal-photo');
  const countEl = document.getElementById('photo-count');
  const medium = currentModal.photos[currentModal.photoIdx];
  if (photoEl) {
    photoEl.classList.remove('no-photo');
    if (photoEl.tagName === 'IMG') photoEl.src = medium;
  }
  if (countEl) {
    countEl.textContent = `${currentModal.photoIdx + 1} / ${currentModal.photos.length}`;
  }
  upgradeModalPhoto();
  if (currentModal.photos.length > 1) {
    const n = currentModal.photos.length;
    preloadLargePhoto(currentModal.photos[(currentModal.photoIdx + 1) % n]);
    preloadLargePhoto(currentModal.photos[(currentModal.photoIdx - 1 + n) % n]);
  }
}

function upgradeModalPhoto() {
  if (!currentModal || !currentModal.photos.length) return;
  const photoEl = document.getElementById('modal-photo');
  if (!photoEl || photoEl.tagName !== 'IMG') return;
  const idx = currentModal.photoIdx;
  const large = largePhotoUrl(currentModal.photos[idx]);
  if (!large || photoEl.src === large) return;
  const img = new Image();
  img.onload = () => {
    if (!currentModal || currentModal.photoIdx !== idx) return;
    photoEl.src = large;
    largePhotoCache.add(large);
  };
  img.src = large;
}

function changeModalPhoto(delta) {
  if (!currentModal || currentModal.photos.length < 2) return;
  const n = currentModal.photos.length;
  currentModal.photoIdx = (currentModal.photoIdx + delta + n) % n;
  renderModalPhoto();
}

function wireGalleryControls() {
  const prev = document.querySelector('[data-photo-prev]');
  const next = document.querySelector('[data-photo-next]');
  if (prev) prev.addEventListener('click', () => changeModalPhoto(-1));
  if (next) next.addEventListener('click', () => changeModalPhoto(1));
  const touchEl = document.querySelector('[data-gallery-touch]');
  if (!touchEl) return;
  touchEl.addEventListener('touchstart', ev => {
    modalTouchStartX = ev.changedTouches && ev.changedTouches[0] ? ev.changedTouches[0].clientX : null;
  }, { passive: true });
  touchEl.addEventListener('touchend', ev => {
    if (modalTouchStartX == null || !ev.changedTouches || !ev.changedTouches[0]) return;
    const dx = ev.changedTouches[0].clientX - modalTouchStartX;
    modalTouchStartX = null;
    if (Math.abs(dx) < 40) return;
    changeModalPhoto(dx < 0 ? 1 : -1);
  }, { passive: true });
}

function sortGroupItems(items) {
  if (sortMode === 'name') {
    const loc = LOCALE_FOR_LANG[displayLang] || 'ja';
    return items.slice().sort((a, b) =>
      displayName(a.sp).localeCompare(displayName(b.sp), loc));
  }
  if (sortMode === 'sci') {
    return items.slice().sort((a, b) =>
      (a.sp.sci || '').localeCompare(b.sp.sci || ''));
  }
  // freq (default): widely-occurring species first
  return items.slice().sort((a, b) => (b.sp.n || 0) - (a.sp.n || 0));
}

function currentFilter() {
  const m = parseInt(document.getElementById('m').value, 10) || 0;
  const g = document.getElementById('g').value || '';
  const q = (document.getElementById('q').value || '').trim().toLowerCase();
  const pk = document.getElementById('park').value;
  const src = document.getElementById('src').value || '';
  return { monthBit: m ? (1<<(m-1)) : 0, group: g, query: q, parking: pk, source: src };
}

function parkPassesParking(park, filter) {
  if (filter.parking === '') return true;
  if (filter.parking === '1') return park.park === 1;
  if (filter.parking === '0') return park.park === 0;
  if (filter.parking === '?') return park.park === null;
  return true;
}

function speciesMatchesFilter(s, f) {
  if (f.group && s.g !== f.group) return false;
  if (f.query) {
    const hay = (s.ja + ' ' + s.sci + ' ' + s.en + ' ' +
                 (s.zh || '') + ' ' + (s.zhT || '')).toLowerCase();
    if (!hay.includes(f.query)) return false;
  }
  return true;
}

function pairMatchesSource(pair, source) {
  if (!source) return true;
  return pair.src && pair.src.includes(source);
}

function pairMatchesMonth(pair, monthBit) {
  if (!monthBit) return true;
  // species without explicit month data (year-round / unknown timing)
  // pass through unconditionally — month is a soft filter that only
  // restricts species WITH known seasonality.
  if (!pair.mb) return true;
  return (pair.mb & monthBit) > 0;
}

function parkMatchesFilter(pi, f) {
  // park matches if park name matches query (when query is set), or
  // if any of its species pairs matches (monthBit + group + query).
  const park = DATA.parks[pi];
  const parkHit = f.query && (park.n.toLowerCase().includes(f.query)
                              || park.s.toLowerCase().includes(f.query));
  if (parkHit) return { reason: 'park-name' };
  for (const pair of parkSpecies[pi]) {
    if (!pairMatchesSource(pair, f.source)) continue;
    if (!pairMatchesMonth(pair, f.monthBit)) continue;
    const sp = DATA.species[pair.si];
    if (!speciesMatchesFilter(sp, f)) continue;
    return { reason: 'species', pair };
  }
  return null;
}

function refreshMap() {
  markerLayer.clearLayers();
  const f = currentFilter();
  let shown = 0, totalSpecies = 0;
  for (let pi = 0; pi < DATA.parks.length; pi++) {
    const park = DATA.parks[pi];
    if (park.lat == null || park.lon == null) continue;
    if (!parkPassesParking(park, f)) continue;
    const hit = parkMatchesFilter(pi, f);
    if (!hit) continue;
    // species count in this park matching filter
    let count = 0;
    for (const pair of parkSpecies[pi]) {
      if (!pairMatchesSource(pair, f.source)) continue;
      if (!pairMatchesMonth(pair, f.monthBit)) continue;
      if (!speciesMatchesFilter(DATA.species[pair.si], f)) continue;
      count++;
    }
    if (count === 0 && hit.reason !== 'park-name') continue;
    const radius = 4 + Math.min(12, Math.sqrt(count));
    const marker = L.circleMarker([park.lat, park.lon], {
      radius, color: '#2a6b3b', weight: 1, fillColor: '#6cae7e', fillOpacity: 0.7,
    }).addTo(markerLayer);
    marker.bindTooltip(`${park.n} (${count})`, { direction: 'top' });
    marker.on('click', () => selectPark(pi, { focusList: true, user: true }));
    shown++; totalSpecies += count;
  }
  statEl.textContent = `${shown} 公園 / ${totalSpecies} 観察記録`;
}

function selectPark(pi, opts = {}) {
  if (opts.user) userSelectedPark = true;
  selectedParkIdx = pi;
  const park = DATA.parks[pi];
  const f = currentFilter();
  const groups = {};
  for (const pair of parkSpecies[pi]) {
    if (!pairMatchesSource(pair, f.source)) continue;
    if (!pairMatchesMonth(pair, f.monthBit)) continue;
    const sp = DATA.species[pair.si];
    if (!speciesMatchesFilter(sp, f)) continue;
    const g = sp.g || '?';
    (groups[g] = groups[g] || []).push({ sp, pair });
  }
  const groupKeys = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);

  const T = labels();
  let html = `<div class="park-title-row"><div class="park-name">${park.n}</div>`
          +  `<button class="park-map-btn" type="button" data-show-map>${T.showMap}</button></div>`;
  html += `<div class="park-meta">${park.pf} ${park.m}`;
  if (park.u) html += ` · <a href="${park.u}" target="_blank">${T.official}</a>`;
  html += `</div>`;
  // parking line
  if (park.park === 1) {
    html += `<div class="parking yes" title="${(park.pi||'').replace(/"/g,'&quot;')}">${T.yes}</div>`;
  } else if (park.park === 0) {
    html += `<div class="parking no" title="${(park.pi||'').replace(/"/g,'&quot;')}">${T.no}</div>`;
  } else {
    html += `<div class="parking unknown">${T.unknown}</div>`;
  }
  let total = 0;
  for (const g of groupKeys) total += groups[g].length;
  html += `<div class="species-count"><span>${T.count(total)}</span>`
       +  `<span class="quick-actions">`
       +  `<button class="quick" type="button" data-select-all>${T.selectAll}</button>`
       +  `<button class="quick" type="button" data-select-none>${T.selectNone}</button>`
       +  `</span></div>`;
  if (total === 0) {
    html += `<div class="placeholder">${T.none}</div>`;
    sideEl.innerHTML = html;
    wirePanelViewButtons();
    if (opts.focusList) showListViewOnMobile();
    return;
  }

  // Controls bar: per-group checkboxes (persistent) + sort selector
  html += `<div class="species-controls">`;
  html += `<div class="row taxa">`;
  for (const g of groupKeys) {
    const checked = selectedGroups.has(g);
    const cls = checked ? 'gck' : 'gck off';
    html += `<label class="${cls}">`
         +  `<input type="checkbox" data-group-cb="${g}"${checked ? ' checked' : ''}/>`
         +  `${groupLabel(g)} (${groups[g].length})`
         +  `</label>`;
  }
  html += `</div>`;
  html += `<div class="row sort">${T.sortLabel}: `;
  html += `<select id="sort-mode">`
       +  `<option value="freq"${sortMode==='freq'?' selected':''}>${T.sortFreq}</option>`
       +  `<option value="name"${sortMode==='name'?' selected':''}>${T.sortName}</option>`
       +  `<option value="sci"${sortMode==='sci'?' selected':''}>${T.sortSci}</option>`
       +  `</select>`;
  html += `</div></div>`;

  const selectedVisibleGroups = groupKeys.filter(g => selectedGroups.has(g));
  if (selectedVisibleGroups.length === 0) {
    html += `<div class="placeholder">${T.none}</div>`;
  }
  for (const g of groupKeys) {
    const items = sortGroupItems(groups[g]);
    const hidden = selectedGroups.has(g) ? '' : ' hidden';
    const autoCollapse = selectedVisibleGroups.length > 1;
    const isCollapsed = autoCollapse ? !expandedGroups.has(g) : false;
    const collapsed = isCollapsed ? ' collapsed' : '';
    const chev = isCollapsed ? '▸' : '▾';
    html += `<div class="group${hidden}${collapsed}" data-group="${g}">`;
    html += `<button class="group-head" type="button" data-collapse-group="${g}" aria-expanded="${isCollapsed ? 'false' : 'true'}">`
         +  `<span class="chev">${chev}</span><span>${groupLabel(g)} (${items.length})</span>`
         +  `</button>`;
    html += `<div class="grid">`;
    const visibleLimit = Math.min(visibleLimitFor(pi, g), items.length);
    for (const { sp, pair } of items.slice(0, visibleLimit)) {
      html += speciesCardHtml(sp, pair);
    }
    html += `</div>`;
    if (items.length > visibleLimit) {
      const remaining = items.length - visibleLimit;
      const nextCount = Math.min(GROUP_LIMIT_STEP, remaining);
      html += `<div class="more-row">`
           +  `<button class="more-btn" type="button" data-more-group="${g}" data-more-count="${nextCount}">${T.showMore(nextCount)}</button>`
           +  `<button class="more-btn" type="button" data-all-group="${g}">${T.showAll(remaining)}</button>`
           +  `</div>`;
    }
    html += `</div>`;
  }
  sideEl.innerHTML = html;
  wirePanelViewButtons();
  if (opts.focusList) showListViewOnMobile();

  // Wire up controls (CSS-only for checkboxes; re-render for sort)
  sideEl.querySelectorAll('[data-group-cb]').forEach(cb => {
    cb.addEventListener('change', () => {
      const g = cb.dataset.groupCb;
      const groupEl = sideEl.querySelector(`.group[data-group="${g}"]`);
      const labelEl = cb.closest('.gck');
      if (cb.checked) {
        selectedGroups.add(g);
        if (groupEl) groupEl.classList.remove('hidden');
        if (labelEl) labelEl.classList.remove('off');
      } else {
        selectedGroups.delete(g);
        expandedGroups.delete(g);
        if (groupEl) groupEl.classList.add('hidden');
        if (labelEl) labelEl.classList.add('off');
      }
      persistSelectedGroups();
      persistExpanded();
      selectPark(selectedParkIdx);
    });
  });
  const selectAllBtn = sideEl.querySelector('[data-select-all]');
  if (selectAllBtn) selectAllBtn.addEventListener('click', () => {
    groupKeys.forEach(g => selectedGroups.add(g));
    expandedGroups.clear();
    persistSelectedGroups();
    persistExpanded();
    selectPark(selectedParkIdx);
  });
  const selectNoneBtn = sideEl.querySelector('[data-select-none]');
  if (selectNoneBtn) selectNoneBtn.addEventListener('click', () => {
    groupKeys.forEach(g => selectedGroups.delete(g));
    expandedGroups.clear();
    persistSelectedGroups();
    persistExpanded();
    selectPark(selectedParkIdx);
  });
  const sortSel = sideEl.querySelector('#sort-mode');
  if (sortSel) sortSel.addEventListener('change', () => {
    sortMode = sortSel.value;
    persistSort();
    selectPark(selectedParkIdx);
  });
  sideEl.querySelectorAll('[data-collapse-group]').forEach(btn => {
    btn.addEventListener('click', () => {
      const g = btn.dataset.collapseGroup;
      const groupEl = sideEl.querySelector(`.group[data-group="${g}"]`);
      const selectedVisibleGroups = groupKeys.filter(key => selectedGroups.has(key));
      const autoCollapse = selectedVisibleGroups.length > 1;
      const isCollapsed = groupEl ? groupEl.classList.contains('collapsed') : autoCollapse;
      const willCollapse = !isCollapsed;
      if (autoCollapse) {
        if (willCollapse) expandedGroups.delete(g);
        else expandedGroups.add(g);
        persistExpanded();
      }
      if (groupEl) groupEl.classList.toggle('collapsed', willCollapse);
      btn.setAttribute('aria-expanded', willCollapse ? 'false' : 'true');
      const chev = btn.querySelector('.chev');
      if (chev) chev.textContent = willCollapse ? '▸' : '▾';
    });
  });
  sideEl.querySelectorAll('[data-more-group]').forEach(btn => {
    btn.addEventListener('click', () => {
      const g = btn.dataset.moreGroup;
      const current = visibleLimitFor(selectedParkIdx, g);
      const add = parseInt(btn.dataset.moreCount || GROUP_LIMIT_STEP, 10);
      setVisibleLimit(selectedParkIdx, g, current + add);
      selectPark(selectedParkIdx);
    });
  });
  sideEl.querySelectorAll('[data-all-group]').forEach(btn => {
    btn.addEventListener('click', () => {
      const g = btn.dataset.allGroup;
      setVisibleLimit(selectedParkIdx, g, Number.MAX_SAFE_INTEGER);
      selectPark(selectedParkIdx);
    });
  });
  sideEl.querySelectorAll('[data-open-species]').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      openSpeciesModal(parseInt(btn.dataset.openSpecies, 10));
    });
  });
}

document.querySelectorAll('[data-modal-close]').forEach(el => {
  el.addEventListener('click', closeSpeciesModal);
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape') closeSpeciesModal();
  if (ev.key === 'ArrowLeft') changeModalPhoto(-1);
  if (ev.key === 'ArrowRight') changeModalPhoto(1);
});

function applyFilters() {
  refreshMap();
  if (selectedParkIdx != null) selectPark(selectedParkIdx);
}

document.getElementById('m').addEventListener('change', applyFilters);
document.getElementById('g').addEventListener('change', applyFilters);
document.getElementById('park').addEventListener('change', applyFilters);
document.getElementById('src').addEventListener('change', applyFilters);
let qTimer = 0;
document.getElementById('q').addEventListener('input', () => {
  clearTimeout(qTimer); qTimer = setTimeout(applyFilters, 200);
});

// language switcher: re-render side panel and update placeholder
const langSel = document.getElementById('lang');
if (langSel) {
  langSel.value = displayLang;
  langSel.addEventListener('change', () => {
    displayLang = langSel.value;
    try { localStorage.setItem(LANG_KEY, displayLang); } catch (e) {}
    if (selectedParkIdx != null) selectPark(selectedParkIdx);
    else {
      const ph = sideEl.querySelector('.placeholder');
      if (ph) ph.innerHTML = labels().placeholder;
    }
    applyView();
  });
}
// On load, replace static placeholder text with localized version
{
  const ph = sideEl.querySelector('.placeholder');
  if (ph) ph.innerHTML = labels().placeholder;
}

refreshMap();

// Mobile view: default split map+detail, marker tap focuses the detail list.
const VIEWS = ['split', 'list'];
let viewIdx = 0;
function isMobileView() {
  return window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
}
function setView(view) {
  const next = VIEWS.indexOf(view);
  if (next < 0 || next === viewIdx) return;
  viewIdx = next;
  applyView();
}
function showListViewOnMobile() {
  if (isMobileView()) setView('list');
}
function showMapViewOnMobile() {
  if (isMobileView()) setView('split');
}
function wirePanelViewButtons() {
  sideEl.querySelectorAll('[data-show-map]').forEach(btn => {
    btn.addEventListener('click', showMapViewOnMobile);
  });
}
function applyView() {
  const v = VIEWS[viewIdx];
  document.body.classList.remove('view-map', 'view-list');
  if (v === 'list') document.body.classList.add('view-list');
  setTimeout(() => map.invalidateSize(), 50);
}
applyView();
window.addEventListener('resize', () => map.invalidateSize());

function distanceKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2
          + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180)
          * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
function isProbablyJapan(lat, lon) {
  return lat >= 24 && lat <= 46 && lon >= 122 && lon <= 146;
}
function nearestParkIdx(lat, lon) {
  let bestIdx = null, bestDist = Infinity;
  for (let pi = 0; pi < DATA.parks.length; pi++) {
    const p = DATA.parks[pi];
    if (p.lat == null || p.lon == null || parkSpecies[pi].length === 0) continue;
    const d = distanceKm(lat, lon, p.lat, p.lon);
    if (d < bestDist) { bestDist = d; bestIdx = pi; }
  }
  return { idx: bestIdx, distanceKm: bestDist };
}
function recommendParkFromPoint(lat, lon, opts = {}) {
  const rec = nearestParkIdx(lat, lon);
  if (rec.idx == null) return false;
  if (opts.requireNearby && rec.distanceKm > MAX_LOCATION_RECOMMEND_KM) return false;
  selectPark(rec.idx);
  const p = DATA.parks[rec.idx];
  map.setView([p.lat, p.lon], opts.zoom || 11);
  return true;
}
function requestLocationRecommendation() {
  if (!navigator.geolocation || !window.isSecureContext) return;
  navigator.geolocation.getCurrentPosition(pos => {
    if (userSelectedPark) return;
    const lat = pos.coords.latitude;
    const lon = pos.coords.longitude;
    if (!isProbablyJapan(lat, lon)) return;
    recommendParkFromPoint(lat, lon, { requireNearby: true, zoom: 12 });
  }, () => {}, { enableHighAccuracy: false, timeout: 5000, maximumAge: 3600000 });
}
recommendParkFromPoint(DEFAULT_RECOMMEND_POINT.lat, DEFAULT_RECOMMEND_POINT.lon, { zoom: 11 });
requestLocationRecommendation();
"""


def main() -> None:
    data = collect_data()
    print(f"species: {len(data['species'])} parks: {len(data['parks'])} pairs: {len(data['pairs'])}")
    present_groups = {sp["g"] for sp in data["species"]}
    group_opts = "".join(
        f"<option value=\"{k}\">{label}</option>" for k, label in GROUP_ORDER
        if k in present_groups
    )
    embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = (HTML_TEMPLATE
            .replace("__GROUP_OPTS__", group_opts)
            .replace("__DATA__", embedded)
            .replace("__SCRIPT__", CLIENT_JS))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"wrote {OUT.relative_to(ROOT)}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
