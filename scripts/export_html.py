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
    ("plant",     "🌸 植物"),
    ("tree",      "🌳 樹木"),
    ("shrub",     "🪴 灌木"),
    ("herb",      "🌿 草本"),
    ("vine",      "🍇 藤本"),
]
PREF_NAMES = {
    "tokyo":    "東京都",
    "kanagawa": "神奈川県",
    "chiba":    "千葉県",
    "saitama":  "埼玉県",
}


def collect_data() -> dict:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        # species: id is the row PK; we pre-collect to use as a dense index
        species_rows = list(conn.execute("""
            SELECT id, scientific_name, common_name_ja, common_name_en,
                   taxon_group, kingdom, photo_url
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

    # build dense indexes (DB ids may have gaps)
    sp_idx = {r["id"]: i for i, r in enumerate(species_rows)}
    pk_idx = {r["id"]: i for i, r in enumerate(park_rows)}

    species = [
        {
            "ja":  r["common_name_ja"] or "",
            "en":  r["common_name_en"] or "",
            "sci": r["scientific_name"] or "",
            "g":   r["taxon_group"] or "",
            "k":   r["kingdom"] or "",
            "p":   r["photo_url"] or "",
            "n":   pop.get(r["id"], 0),
        }
        for r in species_rows
    ]
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
.group h3 { font-size: 13px; margin: 0 0 6px; color: #444; border-bottom: 1px solid #eee;
            padding-bottom: 2px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px,1fr)); gap: 6px; }
.card { background: #f4f4f4; border-radius: 4px; overflow: hidden;
        font-size: 11px; line-height: 1.3; cursor: pointer; }
.card .ph { width: 100%; aspect-ratio: 1 / 1; background: #ddd no-repeat center / cover; }
.card .lab { padding: 4px 6px; }
.card .ja { font-weight: 500; color: #222; }
.card .sci { color: #666; font-style: italic; font-size: 10px; word-break: break-all; }
.card.no-photo .ph { background: linear-gradient(135deg,#cfe7d4,#9bd1a8); }

.legend { font-size: 11px; color: #666; }
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
  bird: '🦜 鳥類', mammal: '🦌 哺乳類', reptile: '🦎 爬虫類',
  amphibian: '🐸 両生類', fish: '🐟 魚類', insect: '🐛 昆虫',
  arachnid: '🕷 クモ類', mollusk: '🐚 軟体動物',
  plant: '🌸 植物', tree: '🌳 樹木', shrub: '🪴 灌木',
  herb: '🌿 草本', vine: '🍇 藤本',
};

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
let hiddenGroups = new Set();
try { hiddenGroups = new Set(JSON.parse(localStorage.getItem(HIDDEN_GROUPS_KEY) || '[]')); }
catch (e) { hiddenGroups = new Set(); }
let sortMode = localStorage.getItem(SORT_KEY) || 'freq'; // 'freq' | 'ja' | 'sci'

function persistHidden() {
  try { localStorage.setItem(HIDDEN_GROUPS_KEY, JSON.stringify([...hiddenGroups])); } catch(e) {}
}
function persistSort() { try { localStorage.setItem(SORT_KEY, sortMode); } catch(e) {} }

function sortGroupItems(items) {
  if (sortMode === 'ja') {
    return items.slice().sort((a, b) =>
      (a.sp.ja || a.sp.sci || '').localeCompare(b.sp.ja || b.sp.sci || '', 'ja'));
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
    const hay = (s.ja + ' ' + s.sci + ' ' + s.en).toLowerCase();
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

  let html = `<div class="park-name">${park.n}</div>`;
  html += `<div class="park-meta">${park.pf} ${park.m}`;
  if (park.u) html += ` · <a href="${park.u}" target="_blank">公式 ↗</a>`;
  html += `</div>`;
  // parking line
  if (park.park === 1) {
    html += `<div class="parking yes" title="${(park.pi||'').replace(/"/g,'&quot;')}">🅿️ 駐車場あり</div>`;
  } else if (park.park === 0) {
    html += `<div class="parking no" title="${(park.pi||'').replace(/"/g,'&quot;')}">🚫 駐車場なし</div>`;
  } else {
    html += `<div class="parking unknown">🅿️ 駐車場情報なし</div>`;
  }
  let total = 0;
  for (const g of groupKeys) total += groups[g].length;
  html += `<div class="species-count">${total} 種が条件に合致</div>`;
  if (total === 0) {
    html += `<div class="placeholder">フィルタに一致する物種なし</div>`;
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
         +  `${GROUP_LABEL[g] || g} (${groups[g].length})`
         +  `</label>`;
  }
  html += `</div>`;
  html += `<div class="row sort">並び順: `;
  html += `<select id="sort-mode">`
       +  `<option value="freq"${sortMode==='freq'?' selected':''}>出現公園数（多→少）</option>`
       +  `<option value="ja"${sortMode==='ja'?' selected':''}>名称（あいうえお）</option>`
       +  `<option value="sci"${sortMode==='sci'?' selected':''}>学名（A→Z）</option>`
       +  `</select>`;
  html += `</div></div>`;

  for (const g of groupKeys) {
    const items = sortGroupItems(groups[g]);
    const hidden = hiddenGroups.has(g) ? ' hidden' : '';
    html += `<div class="group${hidden}" data-group="${g}"><h3>${GROUP_LABEL[g] || g} (${items.length})</h3>`;
    html += `<div class="grid">`;
    for (const { sp, pair } of items.slice(0, 80)) {
      const photo = sp.p ? `style="background-image:url('${sp.p}')"` : '';
      const cls = sp.p ? 'card' : 'card no-photo';
      const name = sp.ja || sp.sci || '?';
      const sci = sp.sci ? `<div class="sci">${sp.sci}</div>` : '';
      html += `<div class="${cls}"><div class="ph" ${photo}></div>` +
              `<div class="lab"><div class="ja">${name}</div>${sci}</div></div>`;
    }
    html += `</div></div>`;
    if (items.length > 80) html += `<div class="legend">…他 ${items.length-80} 種</div>`;
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
}

document.getElementById('m').addEventListener('change', refreshMap);
document.getElementById('g').addEventListener('change', refreshMap);
document.getElementById('park').addEventListener('change', refreshMap);
let qTimer = 0;
document.getElementById('q').addEventListener('input', () => {
  clearTimeout(qTimer); qTimer = setTimeout(refreshMap, 200);
});

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
