/* Thin-client SPA for parklife.
 *
 * Fetches data on demand from static JSON shards produced by
 * scripts/export_static.py, so any dumb static host (GitHub Pages, Cloudflare
 * Pages, S3, ...) serves the whole app with no server. Access pattern:
 *   load        -> data/parks.json                 (light park index, ~150 KB gz)
 *   click park  -> data/parks/<id>.json            (species summary cards)
 *   open species-> data/species/<bucket>.json      (bucketed full profiles)
 *   reverse view-> data/species-parks/<bucket>.json (species -> park-id list)
 *   pair photos -> data/park-photos/<parkId>.json  (park-local gallery)
 *   search      -> data/search-index.json          (loaded once, filtered in JS)
 *
 * Data base is a relative ./data (works under any path prefix incl. GitHub
 * Pages' /repo/ subpath); override with ?data=<base> for a split CDN deploy.
 */
const DATA = new URLSearchParams(location.search).get('data') || './data';
const SPECIES_BUCKETS = 512;  // MUST match BUCKETS in scripts/export_static.py
const _cache = new Map();     // path -> Promise<json> (immutable per deploy)
function getJSON(path) {
  if (_cache.has(path)) return _cache.get(path);
  const pr = fetch(path).then(r => { if (!r.ok) throw new Error(r.status + ' ' + path); return r.json(); });
  pr.catch(() => _cache.delete(path));  // never cache a failed fetch
  _cache.set(path, pr);
  return pr;
}
const bucketOf = (id) => ((id % SPECIES_BUCKETS) + SPECIES_BUCKETS) % SPECIES_BUCKETS;
const dataParks = () => getJSON(DATA + '/parks.json');
const dataPark = (id) => getJSON(DATA + '/parks/' + id + '.json');
async function dataSpecies(id) {
  const b = await getJSON(DATA + '/species/' + bucketOf(id) + '.json');
  return b[id] || null;
}
async function dataSpeciesParkIds(id) {
  const b = await getJSON(DATA + '/species-parks/' + bucketOf(id) + '.json');
  return b[id] || [];
}
async function dataPairPhotos(parkId, sid) {
  try { const m = await getJSON(DATA + '/park-photos/' + parkId + '.json'); return (m && m[sid]) || []; }
  catch { return []; }  // parks with no park-local photos have no file (404)
}
let _searchIdx = null;
async function dataSearch(q, limit) {
  if (!_searchIdx) _searchIdx = await getJSON(DATA + '/search-index.json');
  const ql = q.toLowerCase();
  const hits = [];
  for (const r of _searchIdx) {  // [id, sci, ja, en, zh, zhT, group, p, np]
    if ((r[1] && r[1].toLowerCase().includes(ql)) || (r[2] && r[2].includes(q)) ||
        (r[3] && r[3].toLowerCase().includes(ql)) || (r[4] && r[4].includes(q)) ||
        (r[5] && r[5].includes(q))) hits.push(r);
  }
  hits.sort((a, b) => (b[8] || 0) - (a[8] || 0));  // widest-spread first
  return hits.slice(0, limit).map(r => ({
    id: r[0], sci: r[1], ja: r[2], en: r[3], zh: r[4], zhT: r[5], group: r[6], p: r[7],
  }));
}

// ---- i18n -------------------------------------------------------------------
const LANGS = ['ja', 'en', 'zh', 'zhT'];
const LANG_LABEL = { ja: '日本語', en: 'EN', zh: '简', zhT: '繁' };
// API species.group buckets -> display label (the demo_group buckets).
const GROUP_LABEL = {
  ja: { plant:'🌸 植物', bird:'🦜 鳥類', insect:'🐛 昆虫', arachnid_myriapod:'🕷 クモ・多足類',
    crustacean:'🦀 甲殻類', fish:'🐟 魚類', herp:'🐸 両生・爬虫類', mammal:'🦌 哺乳類',
    mollusk:'🐚 貝・軟体動物', small_aquatic:'🪸 その他水生・小動物', mushroom:'🍄 菌類',
    other_animal:'🐾 その他動物', unclassified:'🐾 その他生き物' },
  en: { plant:'🌸 Plants', bird:'🦜 Birds', insect:'🐛 Insects', arachnid_myriapod:'🕷 Spiders & myriapods',
    crustacean:'🦀 Crustaceans', fish:'🐟 Fish', herp:'🐸 Amphibians & reptiles', mammal:'🦌 Mammals',
    mollusk:'🐚 Shells & molluscs', small_aquatic:'🪸 Other small aquatic animals', mushroom:'🍄 Fungi',
    other_animal:'🐾 Other animals', unclassified:'🐾 Other life' },
  zh: { plant:'🌸 植物', bird:'🦜 鸟类', insect:'🐛 昆虫', arachnid_myriapod:'🕷 蜘蛛与多足类',
    crustacean:'🦀 甲壳类', fish:'🐟 鱼类', herp:'🐸 两栖与爬行动物', mammal:'🦌 哺乳动物',
    mollusk:'🐚 贝类与软体动物', small_aquatic:'🪸 其他水生小动物', mushroom:'🍄 菌类',
    other_animal:'🐾 其他动物', unclassified:'🐾 其他生物' },
  zhT: { plant:'🌸 植物', bird:'🦜 鳥類', insect:'🐛 昆蟲', arachnid_myriapod:'🕷 蜘蛛與多足類',
    crustacean:'🦀 甲殼類', fish:'🐟 魚類', herp:'🐸 兩棲與爬蟲動物', mammal:'🦌 哺乳動物',
    mollusk:'🐚 貝類與軟體動物', small_aquatic:'🪸 其他水生小動物', mushroom:'🍄 菌類',
    other_animal:'🐾 其他動物', unclassified:'🐾 其他生物' },
};
const MONTHS = {
  ja: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
  en: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
  zh: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
  zhT: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
};
const UI = {
  ja: { tagline:'公園の生きもの地図', placeholder:'🗺 地図の公園マーカーをクリック<br>または上の検索ボックスを使ってください',
    species:'種', parking:{1:'🅿️ 駐車場あり',0:'🚫 駐車場なし'}, official:'公式サイト ↗',
    summary:'解説', habitat:'生息環境', tips:'観察のヒント', season:'記録された月', srch:'種・公園を検索',
    seasonUnknown:'通年／不明', parksWith:'この種が見られる公園',
    sort:'並び順', sortFreq:'記録数（多→少）', sortName:'名称', sortSci:'学名 A→Z',
    month:'月', monthAll:'全て', parkingOnly:'🅿️ 駐車場ありのみ', inPark:'この公園での写真', matched:n=>`${n} 種が条件に合致`,
    showMore:n=>`さらに ${n} 種を表示`, showAll:n=>`残り ${n} 種をすべて表示`,
    viewOnMap:'この種が見られる公園を地図で表示', mapFiltered:(name,n)=>`📍 ${name} が見られる ${n} 公園`, showAllParks:'すべての公園に戻る', locate:'現在地に移動' },
  en: { tagline:'A map of life in Japanese parks', placeholder:'🗺 Click a park marker on the map<br>or use the search box above',
    species:'species', parking:{1:'🅿️ Parking',0:'🚫 No parking'}, official:'Official site ↗',
    summary:'About', habitat:'Habitat', tips:'How to find', season:'Recorded months', srch:'Search species / park',
    seasonUnknown:'Year-round / unknown', parksWith:'Parks where this species occurs',
    sort:'Sort', sortFreq:'Record count (high→low)', sortName:'Name', sortSci:'Scientific A→Z',
    month:'Month', monthAll:'All', parkingOnly:'🅿️ Parking only', inPark:'Photos at this park', matched:n=>`${n} species matched`,
    showMore:n=>`Show ${n} more`, showAll:n=>`Show all ${n} remaining`,
    viewOnMap:'Show parks with this species on the map', mapFiltered:(name,n)=>`📍 ${n} parks with ${name}`, showAllParks:'Back to all parks', locate:'My location' },
  zh: { tagline:'日本公园的生物地图', placeholder:'🗺 点击地图上的公园标记<br>或使用上方搜索框',
    species:'种', parking:{1:'🅿️ 有停车场',0:'🚫 无停车场'}, official:'官方网站 ↗',
    summary:'简介', habitat:'栖息环境', tips:'观察提示', season:'记录月份', srch:'搜索物种 / 公园',
    seasonUnknown:'全年／不明', parksWith:'可见到该物种的公园',
    sort:'排序', sortFreq:'记录数（多→少）', sortName:'名称', sortSci:'学名 A→Z',
    month:'月份', monthAll:'全部', parkingOnly:'🅿️ 仅有停车场', inPark:'本公园实拍', matched:n=>`共 ${n} 种符合`,
    showMore:n=>`再显示 ${n} 种`, showAll:n=>`显示剩余全部 ${n} 种`,
    viewOnMap:'在地图上显示有该物种的公园', mapFiltered:(name,n)=>`📍 ${n} 个公园有 ${name}`, showAllParks:'返回全部公园', locate:'我的位置' },
  zhT: { tagline:'日本公園的生物地圖', placeholder:'🗺 點擊地圖上的公園標記<br>或使用上方搜尋框',
    species:'種', parking:{1:'🅿️ 有停車場',0:'🚫 無停車場'}, official:'官方網站 ↗',
    summary:'簡介', habitat:'棲息環境', tips:'觀察提示', season:'記錄月份', srch:'搜尋物種 / 公園',
    seasonUnknown:'全年／不明', parksWith:'可見到該物種的公園',
    sort:'排序', sortFreq:'記錄數（多→少）', sortName:'名稱', sortSci:'學名 A→Z',
    month:'月份', monthAll:'全部', parkingOnly:'🅿️ 僅有停車場', inPark:'本公園實拍', matched:n=>`共 ${n} 種符合`,
    showMore:n=>`再顯示 ${n} 種`, showAll:n=>`顯示剩餘全部 ${n} 種`,
    viewOnMap:'在地圖上顯示有該物種的公園', mapFiltered:(name,n)=>`📍 ${n} 個公園有 ${name}`, showAllParks:'返回全部公園', locate:'我的位置' },
};
const PROFILE_LANG = { ja:'ja', en:'en', zh:'zh', zhT:'zhT' };  // species_profile.lang keys

// ---- state ------------------------------------------------------------------
let lang = localStorage.getItem('pl_lang') || (navigator.language || 'ja').slice(0,2);
if (!LANGS.includes(lang)) lang = lang.startsWith('zh') ? 'zh' : (lang === 'ja' ? 'ja' : 'en');
let curPark = null;       // last loaded park detail
let modalSpecies = null;  // species detail in modal
let modalImgs = [];       // combined gallery shown in modal (park-local + species hero)
let photoIdx = 0;
let sortMode = localStorage.getItem('pl_sort') || 'freq';  // freq | name | sci
let monthFilter = 0;      // 0 = all; 1..12 = that month (soft filter)
let hiddenGroups = new Set();
let parkingOnly = false;
let allParks = [];        // cached light park index for the map filter
let groupShown = {};      // group -> how many cards currently expanded (pagination)
const GROUP_CAP = 48;     // initial cards per group before "show more"
let speciesFilter = null; // {ids:Set<parkId>, name} when showing one species' parks on the map
let userLayer = null;     // Leaflet layer for the user's location dot + accuracy circle
let locateControl = null; // the "my location" map button
let locating = false;     // guard against overlapping geolocation requests

const $ = (id) => document.getElementById(id);
const esc = (s) => (s == null ? '' : String(s)).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const grpLabel = (g) => (GROUP_LABEL[lang][g] || GROUP_LABEL[lang].unclassified);
const dispName = (sp) => (lang === 'ja' ? sp.ja : lang === 'en' ? (sp.en || sp.ja) :
                          lang === 'zh' ? (sp.zh || sp.ja) : (sp.zhT || sp.zh || sp.ja)) || sp.sci;
function monthsText(mb) {
  if (!mb) return UI[lang].seasonUnknown;
  const out = []; for (let i = 0; i < 12; i++) if (mb & (1 << i)) out.push(MONTHS[lang][i]);
  return out.length ? out.join(' · ') : UI[lang].seasonUnknown;
}

// ---- map --------------------------------------------------------------------
let map, cluster;
function initMap() {
  map = L.map('map', { preferCanvas: true }).setView([36.2, 138.2], 5);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, detectRetina: true, attribution: '© OpenStreetMap'
  }).addTo(map);
  cluster = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 50 });
  map.addLayer(cluster);
}
async function loadParks() {
  allParks = await dataParks();
  renderMarkers();
  addParkingControl();
  addLocateControl();
}
function renderMarkers() {
  cluster.clearLayers();
  const markers = [];
  const pts = [];
  for (const p of allParks) {
    if (p.lat == null || p.lon == null) continue;
    if (parkingOnly && p.has_parking !== 1) continue;
    if (speciesFilter && !speciesFilter.ids.has(p.id)) continue;
    const hot = !!speciesFilter;
    const m = L.circleMarker([p.lat, p.lon], { radius: hot ? 7 : 5,
      color: hot ? '#b1430e' : '#2a6b3b', weight: 1,
      fillColor: hot ? '#ff7a3c' : '#4caf6e', fillOpacity: .85 });
    m.on('click', () => openPark(p.id));
    m.bindTooltip(p.name_ja, { direction: 'top' });
    markers.push(m);
    pts.push([p.lat, p.lon]);
  }
  cluster.addLayers(markers);
  if (speciesFilter && pts.length) map.fitBounds(pts, { padding: [40, 40], maxZoom: 12 });
}
async function viewSpeciesOnMap() {
  const s = modalSpecies; if (!s) return;
  const parkIds = await dataSpeciesParkIds(s.id);
  speciesFilter = { ids: new Set(parkIds), name: dispName(s) };
  closeModal();
  renderMarkers();
  const ban = $('mapBanner');
  ban.innerHTML = `<span>${UI[lang].mapFiltered(esc(speciesFilter.name), speciesFilter.ids.size)}</span>`
    + `<button onclick="App.clearSpeciesFilter()">${UI[lang].showAllParks}</button>`;
  ban.style.display = 'flex';
}
function clearSpeciesFilter() {
  speciesFilter = null;
  $('mapBanner').style.display = 'none';
  renderMarkers();
}
let parkingControl = null;
function addParkingControl() {
  if (parkingControl) map.removeControl(parkingControl);
  const C = L.Control.extend({ options: { position: 'topright' },
    onAdd() {
      const el = L.DomUtil.create('label', 'map-ctrl');
      el.innerHTML = `<input type="checkbox"${parkingOnly ? ' checked' : ''}>${UI[lang].parkingOnly}`;
      L.DomEvent.disableClickPropagation(el);
      el.querySelector('input').addEventListener('change', e => { parkingOnly = e.target.checked; renderMarkers(); });
      return el;
    } });
  parkingControl = new C();
  map.addControl(parkingControl);
}

// ---- geolocation (auto-locate on first load + "my location" button) ---------
const isProbablyJapan = (lat, lon) => lat >= 24 && lat <= 46 && lon >= 122 && lon <= 154;
function distanceKm(lat1, lon1, lat2, lon2) {
  const toRad = (d) => d * Math.PI / 180, R = 6371;
  const dLat = toRad(lat2 - lat1), dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
function nearestPark(lat, lon) {
  let best = null, bestKm = Infinity;
  for (const p of allParks) {
    if (p.lat == null || p.lon == null) continue;
    const km = distanceKm(lat, lon, p.lat, p.lon);
    if (km < bestKm) { bestKm = km; best = p; }
  }
  return best ? { park: best, km: bestKm } : null;
}
function showUserLocation(lat, lon, acc) {
  if (!userLayer) userLayer = L.layerGroup().addTo(map);
  userLayer.clearLayers();
  if (acc) L.circle([lat, lon], { radius: acc, color: '#1a73e8', weight: 1,
    fillColor: '#1a73e8', fillOpacity: .12, interactive: false }).addTo(userLayer);
  L.circleMarker([lat, lon], { radius: 7, color: '#fff', weight: 2,
    fillColor: '#1a73e8', fillOpacity: 1 }).addTo(userLayer)
    .bindTooltip(UI[lang].locate, { direction: 'top' });
}
function geolocate(onOk, onFail) {
  if (!navigator.geolocation || !window.isSecureContext) { if (onFail) onFail(); return; }
  navigator.geolocation.getCurrentPosition(
    (pos) => onOk(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy),
    () => { if (onFail) onFail(); },
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 300000 });
}
function setLocateState(s) {  // '' | 'busy' | 'err'
  const b = $('locateBtn'); if (!b) return;
  b.classList.remove('busy', 'err'); if (s) b.classList.add(s);
}
function locateMe() {                       // the "return to my location" button
  if (locating) return;
  locating = true; setLocateState('busy');
  geolocate((lat, lon, acc) => {
    locating = false; setLocateState('');
    showUserLocation(lat, lon, acc);
    map.flyTo([lat, lon], Math.max(map.getZoom(), 13), { duration: .6 });
  }, () => { locating = false; setLocateState('err'); });
}
function autoLocate() {                      // silent recommend-nearest on first load
  geolocate((lat, lon, acc) => {
    if (curPark || location.hash) return;    // user already navigated meanwhile
    if (!isProbablyJapan(lat, lon)) return;
    showUserLocation(lat, lon, acc);
    map.setView([lat, lon], 12);
    const near = nearestPark(lat, lon);
    if (near && near.km <= 30) openPark(near.park.id, false);
  });
}
function addLocateControl() {
  if (locateControl) return;
  const C = L.Control.extend({ options: { position: 'topleft' },
    onAdd() {
      const bar = L.DomUtil.create('div', 'leaflet-bar');
      const el = L.DomUtil.create('a', 'map-locate', bar);
      el.href = '#'; el.id = 'locateBtn'; el.innerHTML = '◎';
      el.title = UI[lang].locate;
      el.setAttribute('role', 'button'); el.setAttribute('aria-label', UI[lang].locate);
      L.DomEvent.on(el, 'click', (e) => { L.DomEvent.stop(e); locateMe(); });
      L.DomEvent.disableClickPropagation(bar);
      return bar;
    } });
  locateControl = new C();
  map.addControl(locateControl);
}

// ---- deep-linking (shareable #park/<id> · #species/<id> + back/forward) ------
function setHash(h, push) {
  const target = h || (location.pathname + location.search);
  if (location.hash === (h || '')) return;
  if (push) history.pushState(null, '', target);
  else history.replaceState(null, '', target);
}
function hideModal() { $('modal').classList.remove('on'); modalSpecies = null; modalImgs = []; }
async function applyHash() {
  const m = location.hash.match(/^#(park|species)\/(\d+)$/);
  if (!m) { hideModal(); return; }
  if (m[1] === 'park') {
    hideModal();
    if (!curPark || curPark.id !== +m[2]) await openPark(+m[2], false);
  } else if (!modalSpecies || modalSpecies.id !== +m[2]) {
    await openSpecies(+m[2], curPark ? curPark.id : null, false);
  }
}

// ---- park panel -------------------------------------------------------------
async function openPark(id, push = true) {
  $('panel').innerHTML = '<div class="placeholder">…</div>';
  const p = await dataPark(id);
  curPark = p;
  groupShown = {};
  renderPark();
  setHash('#park/' + id, push);
  if (window.matchMedia('(max-width: 760px)').matches) $('panel').scrollIntoView({ behavior: 'smooth' });
}
const GROUP_ORDER = ['plant','bird','insect','mammal','herp','fish','mollusk','crustacean',
                     'arachnid_myriapod','mushroom','small_aquatic','other_animal','unclassified'];
function speciesCard(s) {
  const bg = s.p ? `background-image:url('${esc(s.p)}')` : '';
  return `<div class="card" onclick="App.openSpecies(${s.id},${curPark ? curPark.id : 'null'})">`
       + `<div class="ph" style="${bg}"></div>`
       + `<div class="nm"><b>${esc(dispName(s))}</b><i>${esc(s.sci || '')}</i></div></div>`;
}
function sortSpecies(arr) {
  const a = arr.slice();
  if (sortMode === 'name') a.sort((x, y) => dispName(x).localeCompare(dispName(y)));
  else if (sortMode === 'sci') a.sort((x, y) => (x.sci || '~').localeCompare(y.sci || '~'));
  else a.sort((x, y) => (y.oc || 0) - (x.oc || 0) || (y.sc || 0) - (x.sc || 0));
  return a;
}
function passMonth(s) {
  if (!monthFilter) return true;
  if (!s.mb) return true;               // unknown/year-round passes (soft filter)
  return (s.mb & (1 << (monthFilter - 1))) !== 0;
}
function renderPark() {
  const p = curPark; if (!p) return;
  const U = UI[lang];
  const name = (lang === 'ja' ? p.name_ja : (p.name_en || p.name_ja)) || p.name_ja;
  const meta = [];
  if (p.has_parking === 1 || p.has_parking === 0) meta.push(U.parking[p.has_parking]);
  if (p.official_url) meta.push(`<a href="${esc(p.official_url)}" target="_blank" rel="noopener">${U.official}</a>`);

  const shown = p.species.filter(passMonth);
  const byGrp = {};
  for (const s of shown) (byGrp[s.group || 'unclassified'] ||= []).push(s);
  const groups = Object.keys(byGrp).sort((a, b) =>
    (GROUP_ORDER.indexOf(a) + 1 || 99) - (GROUP_ORDER.indexOf(b) + 1 || 99));

  const monthOpts = [`<option value="0">${U.monthAll}</option>`]
    .concat(MONTHS[lang].map((m, i) => `<option value="${i + 1}"${monthFilter === i + 1 ? ' selected' : ''}>${m}</option>`)).join('');
  let html = `<div class="park-name">${esc(name)}</div>`
    + `<div class="park-meta">${U.matched(shown.length)}${meta.length ? ' · ' + meta.join(' · ') : ''}</div>`
    + `<div class="controls">`
    + `<span>${U.sort}: <select onchange="App.setSort(this.value)">`
    + `<option value="freq"${sortMode==='freq'?' selected':''}>${U.sortFreq}</option>`
    + `<option value="name"${sortMode==='name'?' selected':''}>${U.sortName}</option>`
    + `<option value="sci"${sortMode==='sci'?' selected':''}>${U.sortSci}</option></select></span>`
    + `<span>${U.month}: <select onchange="App.setMonth(this.value)">${monthOpts}</select></span>`
    + `</div>`;
  for (const g of groups) {
    const off = hiddenGroups.has(g) ? ' off' : '';
    const list = sortSpecies(byGrp[g]);
    const shownN = Math.min(list.length, groupShown[g] || GROUP_CAP);
    html += `<div class="grp-h${off}" onclick="App.toggleGroup('${g}')">${grpLabel(g)} `
          + `<span class="count">(${list.length})</span></div><div class="grid">`;
    html += list.slice(0, shownN).map(speciesCard).join('');
    html += '</div>';
    const rest = list.length - shownN;
    if (rest > 0 && !hiddenGroups.has(g)) {
      const step = Math.min(rest, 96);
      html += `<button class="more-btn" onclick="App.showMore('${g}',${step})">${U.showMore(step)}</button>`;
      if (rest > step) html += `<button class="more-btn" onclick="App.showMore('${g}',${rest})">${U.showAll(rest)}</button>`;
    }
  }
  $('panel').innerHTML = html;
}
function showMore(g, n) { groupShown[g] = (groupShown[g] || GROUP_CAP) + n; renderPark(); }
function setSort(v) { sortMode = v; localStorage.setItem('pl_sort', v); renderPark(); }
function setMonth(v) { monthFilter = +v; renderPark(); }
function toggleGroup(g) { if (hiddenGroups.has(g)) hiddenGroups.delete(g); else hiddenGroups.add(g); renderPark(); }

// ---- species modal ----------------------------------------------------------
async function openSpecies(id, parkId, push = true) {
  const reqs = [dataSpecies(id)];
  if (parkId != null) reqs.push(dataPairPhotos(parkId, id));
  const [s, parkPhotos] = await Promise.all(reqs);
  if (!s) return;  // deep-link to an unknown/unreachable species id
  modalSpecies = s; photoIdx = 0;
  setHash('#species/' + id, push);
  // Combine: park-local photos first (flagged), then the species hero gallery.
  const local = (parkPhotos || []).map(p => p.concat(['__local__']));
  modalImgs = local.concat(s.imgs || []);
  if (!modalImgs.length && s.p) modalImgs = [[s.p, '', '', '']];
  renderModal();
  $('modal').classList.add('on');
}
function renderModal() {
  const s = modalSpecies; if (!s) return;
  const U = UI[lang];
  const imgs = modalImgs;
  const cur = imgs[photoIdx];
  let ph = '';
  if (cur) {
    const [url, attr, src] = cur;
    const isLocal = cur[cur.length - 1] === '__local__';
    const nav = imgs.length > 1
      ? `<button class="nav l" onclick="App.photo(-1)">‹</button><button class="nav r" onclick="App.photo(1)">›</button>` : '';
    const badge = isLocal ? `<span style="background:#2a6b3b;padding:1px 6px;border-radius:8px;margin-right:6px">📍 ${U.inPark}</span>` : '';
    const a = (attr || isLocal) ? `<div class="attr">${badge}${src ? `<a href="${esc(src)}" target="_blank" rel="noopener">${esc(attr)}</a>` : esc(attr)}</div>` : '';
    ph = `<div style="position:absolute;inset:0;background:#222 url('${esc(url)}') center/contain no-repeat"></div>${nav}${a}`;
  }
  $('mphoto').innerHTML = ph;

  const pr = (s.pr && (s.pr[PROFILE_LANG[lang]] || s.pr.en || s.pr.ja)) || null;
  const alt = [];
  if (lang !== 'ja' && s.ja) alt.push(s.ja);
  if (lang !== 'zh' && s.zh) alt.push(s.zh);
  if (lang !== 'en' && s.en) alt.push(s.en);
  let body = `<h2>${esc(dispName(s))}</h2><div class="sci">${esc(s.sci || '')}</div>`;
  body += `<div class="alt">${esc(alt.join(' · '))}</div>`;
  body += `<div><span class="pill">${grpLabel(s.group)}</span>`
        + `<button class="more-btn" onclick="App.viewSpeciesOnMap()">🗺 ${U.viewOnMap}</button></div>`;
  if (pr) {
    if (pr.summary)      body += `<div class="sec"><b>${U.summary}</b>${esc(pr.summary)}</div>`;
    if (pr.habitat_hint) body += `<div class="sec"><b>${U.habitat}</b>${esc(pr.habitat_hint)}</div>`;
    if (pr.finding_tips) body += `<div class="sec"><b>${U.tips}</b>${esc(pr.finding_tips)}</div>`;
  }
  $('mbody').innerHTML = body;
}
function photo(d) {
  const n = modalImgs.length; if (!n) return;
  photoIdx = (photoIdx + d + n) % n; renderModal();
}
function closeModal() {
  $('modal').classList.remove('on'); modalSpecies = null; modalImgs = [];
  if (/^#species\//.test(location.hash)) setHash(curPark ? '#park/' + curPark.id : '', false);
}

// ---- search -----------------------------------------------------------------
let searchTimer = null;
function onSearch(e) {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (q.length < 2) return;
  searchTimer = setTimeout(async () => {
    const res = await dataSearch(q, 24);
    curPark = null;  // search context: cards open without a park
    let html = `<div class="park-name">🔍 ${esc(q)}</div><div class="park-meta">${res.length} ${UI[lang].species}</div><div class="grid">`;
    html += res.map(speciesCard).join('');
    html += '</div>';
    $('panel').innerHTML = html;
  }, 280);
}

// ---- chrome -----------------------------------------------------------------
function setLang(l) {
  lang = l; localStorage.setItem('pl_lang', l);
  document.documentElement.lang = l === 'zhT' ? 'zh-Hant' : l;
  renderChrome();
  if (map) addParkingControl();  // its label is language-dependent
  { const lb = $('locateBtn'); if (lb) { lb.title = UI[lang].locate; lb.setAttribute('aria-label', UI[lang].locate); } }
  if (modalSpecies) renderModal();
  if (curPark) renderPark(); else $('ph').innerHTML = UI[lang].placeholder;
  if (speciesFilter) {  // refresh the reverse-view banner in the new language
    $('mapBanner').innerHTML =
      `<span>${UI[lang].mapFiltered(esc(speciesFilter.name), speciesFilter.ids.size)}</span>`
      + `<button onclick="App.clearSpeciesFilter()">${UI[lang].showAllParks}</button>`;
  }
}
function renderChrome() {
  $('tagline').textContent = UI[lang].tagline;
  $('search').placeholder = UI[lang].srch;
  $('lang').innerHTML = LANGS.map(l =>
    `<button class="${l === lang ? 'on' : ''}" onclick="App.setLang('${l}')">${LANG_LABEL[l]}</button>`).join('');
}

const App = { openPark, openSpecies, setLang, closeModal, photo, setSort, setMonth, toggleGroup, showMore,
              viewSpeciesOnMap, clearSpeciesFilter };
window.App = App;

(function main() {
  renderChrome();
  $('ph').innerHTML = UI[lang].placeholder;
  $('search').addEventListener('input', onSearch);
  $('modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    if (modalSpecies && e.key === 'ArrowLeft') photo(-1);
    if (modalSpecies && e.key === 'ArrowRight') photo(1);
  });
  window.addEventListener('hashchange', applyHash);  // back/forward + manual edits (pushState doesn't fire this)
  initMap();
  loadParks()
    .then(() => { applyHash(); if (!location.hash) autoLocate(); })  // shared link, else auto-locate
    .catch(err => { $('ph').innerHTML = 'load error: ' + esc(err.message); });
})();
