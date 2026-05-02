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

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "export" / "index.html"

# Render order for taxon group dropdown
GROUP_ORDER = [
    ("bird",      "🦜 鳥類"),
    ("mammal",    "🦌 哺乳類"),
    ("reptile",   "🦎 爬虫類"),
    ("amphibian", "🐸 両生類"),
    ("fish",      "🐟 魚類"),
    ("insect",    "🐛 昆虫"),
    ("arachnid",  "🕷 クモ類"),
    ("mollusk",   "🐚 軟体動物"),
    ("other_animal", "🐾 その他動物"),
    ("plant",     "🌸 植物"),
    ("mushroom",  "🍄 菌類"),
    ("unclassified", "❓ 未分類"),
]
PREF_NAMES = {
    "tokyo":    "東京都",
    "kanagawa": "神奈川県",
    "chiba":    "千葉県",
    "saitama":  "埼玉県",
}


def demo_group(taxon_group: str | None, kingdom: str | None) -> str:
    """Map DB taxonomy to user-facing demo buckets."""
    if taxon_group in {"plant", "tree", "shrub", "herb", "vine", "fern", "moss"}:
        return "plant"
    if taxon_group:
        return taxon_group
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
            SELECT park_id, species_id, months_bitmap, source_count
            FROM park_species
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

    # build dense indexes (DB ids may have gaps)
    pk_idx = {r["id"]: i for i, r in enumerate(park_rows)}

    species = []
    sp_idx = {}
    for r in species_rows:
        group = demo_group(r["taxon_group"], r["kingdom"])
        if not group:
            continue
        sp_idx[r["id"]] = len(species)
        species.append({
            "ja":   r["common_name_ja"] or "",
            "en":   r["common_name_en"] or "",
            "zh":   zh_hans.get(r["id"], ""),
            "zhT":  zh_hant.get(r["id"], ""),
            "sci":  r["scientific_name"] or "",
            "g":    group,
            "k":    r["kingdom"] or "",
            "p":    r["photo_url"] or "",
            "tid":  r["inat_taxon_id"] or 0,
            "eb":   ebird_code.get(r["id"], ""),
            "n":    pop.get(r["id"], 0),
        })
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
    pairs = []
    for r in pair_rows:
        pi = pk_idx.get(r["park_id"])
        si = sp_idx.get(r["species_id"])
        if pi is None or si is None:
            continue
        pairs.append([pi, si, r["months_bitmap"] or 0, r["source_count"] or 1])

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
.park-name { font-size: 18px; font-weight: 600; margin: 4px 0 2px; }
.park-meta { font-size: 12px; color: #666; }
.park-meta a { color: #2a6b3b; }
.species-count { margin: 8px 0; font-size: 13px; color: #444; }
.species-controls { position: sticky; top: 0; background: #fff; padding: 6px 0 8px;
                    margin-top: 6px; border-bottom: 1px solid #eee; z-index: 5; }
.species-controls .row { display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: center; }
.species-controls .row.sort { margin-top: 6px; font-size: 12px; color: #555; }
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
.card { background: #f4f4f4; border-radius: 4px; overflow: hidden;
        font-size: 11px; line-height: 1.3; }
.card .ph { width: 100%; aspect-ratio: 1 / 1; background: #ddd no-repeat center / cover; }
.card .lab { padding: 4px 6px; min-height: 54px; display: flex; flex-direction: column; gap: 2px; }
.card .ja { font-weight: 500; color: #222; }
.card .sci { color: #666; font-style: italic; font-size: 10px; word-break: break-all; }
.card .links { margin-top: auto; display: flex; justify-content: flex-end; gap: 4px; }
.card .links a { color: #2a6b3b; border: 1px solid #c9d8cc; background: #fff;
                 border-radius: 3px; padding: 1px 4px; font-size: 10px;
                 text-decoration: none; font-style: normal; }
.card .links a:hover { background: #e8f4eb; }
.card.no-photo .ph { background: linear-gradient(135deg,#cfe7d4,#9bd1a8); }

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

/* mobile toggle: hidden on desktop, visible <=768px */
#view-toggle { display: none; }

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

  /* full-view modes */
  body.view-map #side { display: none; }
  body.view-map #map  { height: calc(100vh - 90px); }
  body.view-list #map { display: none; }
  body.view-list #side { height: calc(100vh - 90px); }

  #view-toggle {
    display: block; position: fixed; right: 10px; bottom: 10px; z-index: 1000;
    background: #2a6b3b; color: #fff; border: none; border-radius: 24px;
    padding: 10px 14px; font-size: 14px; box-shadow: 0 2px 8px rgba(0,0,0,.25);
    cursor: pointer;
  }

  .grid { grid-template-columns: repeat(auto-fill, minmax(96px,1fr)); }
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
<button id="view-toggle" type="button" aria-label="切り替え">📋 一覧</button>

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
    arachnid: '🕷 クモ類', mollusk: '🐚 軟体動物',
    other_animal: '🐾 その他動物',
    plant: '🌸 植物', mushroom: '🍄 菌類',
    unclassified: '❓ 未分類',
  },
  en: {
    bird: '🦜 Birds', mammal: '🦌 Mammals', reptile: '🦎 Reptiles',
    amphibian: '🐸 Amphibians', fish: '🐟 Fish', insect: '🐛 Insects',
    arachnid: '🕷 Arachnids', mollusk: '🐚 Molluscs',
    other_animal: '🐾 Other animals',
    plant: '🌸 Plants', mushroom: '🍄 Fungi',
    unclassified: '❓ Unclassified',
  },
  zh: {
    bird: '🦜 鸟类', mammal: '🦌 哺乳动物', reptile: '🦎 爬行动物',
    amphibian: '🐸 两栖动物', fish: '🐟 鱼类', insect: '🐛 昆虫',
    arachnid: '🕷 蛛形纲', mollusk: '🐚 软体动物',
    other_animal: '🐾 其他动物',
    plant: '🌸 植物', mushroom: '🍄 菌类',
    unclassified: '❓ 未分类',
  },
  zhT: {
    bird: '🦜 鳥類', mammal: '🦌 哺乳動物', reptile: '🦎 爬蟲動物',
    amphibian: '🐸 兩棲動物', fish: '🐟 魚類', insect: '🐛 昆蟲',
    arachnid: '🕷 蛛形綱', mollusk: '🐚 軟體動物',
    other_animal: '🐾 其他動物',
    plant: '🌸 植物', mushroom: '🍄 菌類',
    unclassified: '❓ 未分類',
  },
};

const PARKING_LABELS = {
  ja: { yes: '🅿️ 駐車場あり', no: '🚫 駐車場なし', unknown: '🅿️ 駐車場情報なし', count: n => `${n} 種が条件に合致`, none: 'フィルタに一致する物種なし', sortLabel: '並び順', sortFreq: '出現公園数（多→少）', sortName: '名称', sortSci: '学名（A→Z）', overflow: n => `…他 ${n} 種`, showMore: n => `さらに ${n} 種を表示`, showAll: n => `残り ${n} 種をすべて表示`, official: '公式 ↗', placeholder: '📍 地図上の公園マーカーをクリック<br/>または右上の検索ボックスを使用' },
  en: { yes: '🅿️ Parking available', no: '🚫 No parking', unknown: '🅿️ Parking unknown', count: n => `${n} species matched`, none: 'No species match the filter', sortLabel: 'Sort', sortFreq: 'Park count (high→low)', sortName: 'Name', sortSci: 'Scientific name (A→Z)', overflow: n => `…and ${n} more`, showMore: n => `Show ${n} more`, showAll: n => `Show all ${n} remaining`, official: 'Official ↗', placeholder: '📍 Click a park marker on the map<br/>or use the search box' },
  zh: { yes: '🅿️ 有停车场', no: '🚫 无停车场', unknown: '🅿️ 停车场信息未知', count: n => `共 ${n} 种符合条件`, none: '没有符合筛选条件的物种', sortLabel: '排序', sortFreq: '公园数（多→少）', sortName: '名称', sortSci: '学名（A→Z）', overflow: n => `…还有 ${n} 种`, showMore: n => `再显示 ${n} 种`, showAll: n => `显示剩余全部 ${n} 种`, official: '官网 ↗', placeholder: '📍 点击地图上的公园标记<br/>或使用右上角搜索框' },
  zhT: { yes: '🅿️ 有停車場', no: '🚫 無停車場', unknown: '🅿️ 停車場資訊未知', count: n => `共 ${n} 種符合條件`, none: '沒有符合篩選條件的物種', sortLabel: '排序', sortFreq: '公園數（多→少）', sortName: '名稱', sortSci: '學名（A→Z）', overflow: n => `…還有 ${n} 種`, showMore: n => `再顯示 ${n} 種`, showAll: n => `顯示剩餘全部 ${n} 種`, official: '官網 ↗', placeholder: '📍 點擊地圖上的公園標記<br/>或使用右上角搜尋框' },
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
  return (GROUP_LABEL[displayLang] || GROUP_LABEL.ja)[g] || g;
}
function labels() { return PARKING_LABELS[displayLang] || PARKING_LABELS.ja; }

// Build per-park indices (which species are at each park, with months)
const parkSpecies = DATA.parks.map(()=> []);
for (const [pi, si, mb, sc] of DATA.pairs) {
  parkSpecies[pi].push({si, mb, sc});
}

const map = L.map('map', { zoomControl: true }).setView([35.65, 139.7], 9);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 18, attribution: '© OpenStreetMap'
}).addTo(map);

const markerLayer = L.layerGroup().addTo(map);
const sideEl = document.getElementById('side');
const statEl = document.getElementById('stat');
let selectedParkIdx = null;

// Per-park species panel: persistent group-checkbox + sort state
const HIDDEN_GROUPS_KEY = 'parklife.hiddenGroups';
const SORT_KEY = 'parklife.speciesSort';
const COLLAPSED_GROUPS_KEY = 'parklife.collapsedGroups';
const GROUP_LIMIT_STEP = 80;
let hiddenGroups = new Set();
try { hiddenGroups = new Set(JSON.parse(localStorage.getItem(HIDDEN_GROUPS_KEY) || '[]')); }
catch (e) { hiddenGroups = new Set(); }
let sortMode = localStorage.getItem(SORT_KEY) || 'freq'; // 'freq' | 'name' | 'sci'
if (sortMode === 'ja') sortMode = 'name'; // migration from old key
let collapsedGroups = new Set();
try { collapsedGroups = new Set(JSON.parse(localStorage.getItem(COLLAPSED_GROUPS_KEY) || '[]')); }
catch (e) { collapsedGroups = new Set(); }
let expandedGroupLimits = {};

function persistHidden() {
  try { localStorage.setItem(HIDDEN_GROUPS_KEY, JSON.stringify([...hiddenGroups])); } catch(e) {}
}
function persistSort() { try { localStorage.setItem(SORT_KEY, sortMode); } catch(e) {} }
function persistCollapsed() {
  try { localStorage.setItem(COLLAPSED_GROUPS_KEY, JSON.stringify([...collapsedGroups])); } catch(e) {}
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

function speciesCardHtml(sp) {
  const photo = sp.p ? `style="background-image:url('${sp.p}')"` : '';
  const cls = sp.p ? 'card' : 'card no-photo';
  const name = displayName(sp);
  const sci = sp.sci ? `<div class="sci">${sp.sci}</div>` : '';
  const wiki = `<a href="${wikiSearchUrl(sp)}" target="_blank" rel="noopener" title="Wikipedia">Wiki</a>`;
  const inat = sp.tid ? `<a href="${inatTaxonUrl(sp)}" target="_blank" rel="noopener" title="iNaturalist">iNat</a>` : '';
  const ebird = sp.eb ? `<a href="${ebirdSpeciesUrl(sp)}" target="_blank" rel="noopener" title="eBird">eBird</a>` : '';
  const links = `<div class="links">${wiki}${inat}${ebird}</div>`;
  return `<div class="${cls}"><div class="ph" ${photo}></div>` +
         `<div class="lab"><div class="ja">${name}</div>${sci}${links}</div></div>`;
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
  return { monthBit: m ? (1<<(m-1)) : 0, group: g, query: q, parking: pk };
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
    marker.on('click', () => selectPark(pi));
    shown++; totalSpecies += count;
  }
  statEl.textContent = `${shown} 公園 / ${totalSpecies} 観察記録`;
}

function selectPark(pi) {
  selectedParkIdx = pi;
  const park = DATA.parks[pi];
  const f = currentFilter();
  const groups = {};
  for (const pair of parkSpecies[pi]) {
    if (!pairMatchesMonth(pair, f.monthBit)) continue;
    const sp = DATA.species[pair.si];
    if (!speciesMatchesFilter(sp, f)) continue;
    const g = sp.g || '?';
    (groups[g] = groups[g] || []).push({ sp, pair });
  }
  const groupKeys = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);

  const T = labels();
  let html = `<div class="park-name">${park.n}</div>`;
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
  html += `<div class="species-count">${T.count(total)}</div>`;
  if (total === 0) {
    html += `<div class="placeholder">${T.none}</div>`;
    sideEl.innerHTML = html;
    return;
  }

  // Controls bar: per-group checkboxes (persistent) + sort selector
  html += `<div class="species-controls">`;
  html += `<div class="row taxa">`;
  for (const g of groupKeys) {
    const checked = !hiddenGroups.has(g);
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

  for (const g of groupKeys) {
    const items = sortGroupItems(groups[g]);
    const hidden = hiddenGroups.has(g) ? ' hidden' : '';
    const collapsed = collapsedGroups.has(g) ? ' collapsed' : '';
    const chev = collapsedGroups.has(g) ? '▸' : '▾';
    html += `<div class="group${hidden}${collapsed}" data-group="${g}">`;
    html += `<button class="group-head" type="button" data-collapse-group="${g}" aria-expanded="${collapsed ? 'false' : 'true'}">`
         +  `<span class="chev">${chev}</span><span>${groupLabel(g)} (${items.length})</span>`
         +  `</button>`;
    html += `<div class="grid">`;
    const visibleLimit = Math.min(visibleLimitFor(pi, g), items.length);
    for (const { sp } of items.slice(0, visibleLimit)) {
      html += speciesCardHtml(sp);
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

  // Wire up controls (CSS-only for checkboxes; re-render for sort)
  sideEl.querySelectorAll('[data-group-cb]').forEach(cb => {
    cb.addEventListener('change', () => {
      const g = cb.dataset.groupCb;
      const groupEl = sideEl.querySelector(`.group[data-group="${g}"]`);
      const labelEl = cb.closest('.gck');
      if (cb.checked) {
        hiddenGroups.delete(g);
        if (groupEl) groupEl.classList.remove('hidden');
        if (labelEl) labelEl.classList.remove('off');
      } else {
        hiddenGroups.add(g);
        if (groupEl) groupEl.classList.add('hidden');
        if (labelEl) labelEl.classList.add('off');
      }
      persistHidden();
    });
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
      const willCollapse = !collapsedGroups.has(g);
      if (willCollapse) collapsedGroups.add(g);
      else collapsedGroups.delete(g);
      if (groupEl) groupEl.classList.toggle('collapsed', willCollapse);
      btn.setAttribute('aria-expanded', willCollapse ? 'false' : 'true');
      const chev = btn.querySelector('.chev');
      if (chev) chev.textContent = willCollapse ? '▸' : '▾';
      persistCollapsed();
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
}

document.getElementById('m').addEventListener('change', refreshMap);
document.getElementById('g').addEventListener('change', refreshMap);
document.getElementById('park').addEventListener('change', refreshMap);
let qTimer = 0;
document.getElementById('q').addEventListener('input', () => {
  clearTimeout(qTimer); qTimer = setTimeout(refreshMap, 200);
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
  });
}
// On load, replace static placeholder text with localized version
{
  const ph = sideEl.querySelector('.placeholder');
  if (ph) ph.innerHTML = labels().placeholder;
}

refreshMap();

// Mobile view toggle (split / map-only / list-only)
const toggleBtn = document.getElementById('view-toggle');
const VIEWS = ['split', 'map', 'list'];
const LABELS = { split: '🗺 全画面地図', map: '📋 一覧', list: '🗺 地図' };
let viewIdx = 0;
function applyView() {
  const v = VIEWS[viewIdx];
  document.body.classList.remove('view-map', 'view-list');
  if (v === 'map')  document.body.classList.add('view-map');
  if (v === 'list') document.body.classList.add('view-list');
  toggleBtn.textContent = LABELS[VIEWS[(viewIdx + 1) % VIEWS.length]];
  setTimeout(() => map.invalidateSize(), 50);
}
toggleBtn.addEventListener('click', () => {
  viewIdx = (viewIdx + 1) % VIEWS.length;
  applyView();
});
applyView();
window.addEventListener('resize', () => map.invalidateSize());

// initial selection: most-diverse park visible
let bestIdx = 0, bestN = 0;
for (let pi = 0; pi < DATA.parks.length; pi++) {
  const n = parkSpecies[pi].length;
  if (n > bestN) { bestN = n; bestIdx = pi; }
}
selectPark(bestIdx);
"""


def main() -> None:
    data = collect_data()
    print(f"species: {len(data['species'])} parks: {len(data['parks'])} pairs: {len(data['pairs'])}")
    group_opts = "".join(
        f"<option value=\"{k}\">{label}</option>" for k, label in GROUP_ORDER
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
