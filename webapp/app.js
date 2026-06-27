/* Thin-client SPA for parklife.
 *
 * Fetches data on demand from the read-only API (scripts/serve_api.py) instead
 * of downloading the whole 69 MB parklife-data.json. Access pattern:
 *   load        -> GET /api/parks            (~0.8 MB, all park markers)
 *   click park  -> GET /api/parks/<id>       (~150 KB, species summary cards)
 *   open species-> GET /api/species/<id>     (~5 KB, profile + photo gallery)
 *   search box  -> GET /api/search?q=...
 *
 * API base is same-origin /api when served by serve_api; override with
 * ?api=<base> for a split deploy.
 */
const API = new URLSearchParams(location.search).get('api') || '/api';
const j = (path) => fetch(API + path).then(r => { if (!r.ok) throw new Error(r.status + ' ' + path); return r.json(); });

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
    seasonUnknown:'通年／不明', parksWith:'この種が見られる公園' },
  en: { tagline:'A map of life in Japanese parks', placeholder:'🗺 Click a park marker on the map<br>or use the search box above',
    species:'species', parking:{1:'🅿️ Parking',0:'🚫 No parking'}, official:'Official site ↗',
    summary:'About', habitat:'Habitat', tips:'How to find', season:'Recorded months', srch:'Search species / park',
    seasonUnknown:'Year-round / unknown', parksWith:'Parks where this species occurs' },
  zh: { tagline:'日本公园的生物地图', placeholder:'🗺 点击地图上的公园标记<br>或使用上方搜索框',
    species:'种', parking:{1:'🅿️ 有停车场',0:'🚫 无停车场'}, official:'官方网站 ↗',
    summary:'简介', habitat:'栖息环境', tips:'观察提示', season:'记录月份', srch:'搜索物种 / 公园',
    seasonUnknown:'全年／不明', parksWith:'可见到该物种的公园' },
  zhT: { tagline:'日本公園的生物地圖', placeholder:'🗺 點擊地圖上的公園標記<br>或使用上方搜尋框',
    species:'種', parking:{1:'🅿️ 有停車場',0:'🚫 無停車場'}, official:'官方網站 ↗',
    summary:'簡介', habitat:'棲息環境', tips:'觀察提示', season:'記錄月份', srch:'搜尋物種 / 公園',
    seasonUnknown:'全年／不明', parksWith:'可見到該物種的公園' },
};
const PROFILE_LANG = { ja:'ja', en:'en', zh:'zh', zhT:'zhT' };  // species_profile.lang keys

// ---- state ------------------------------------------------------------------
let lang = localStorage.getItem('pl_lang') || (navigator.language || 'ja').slice(0,2);
if (!LANGS.includes(lang)) lang = lang.startsWith('zh') ? 'zh' : (lang === 'ja' ? 'ja' : 'en');
let curPark = null;       // last loaded park detail
let modalSpecies = null;  // species detail in modal
let photoIdx = 0;

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
    maxZoom: 19, attribution: '© OpenStreetMap'
  }).addTo(map);
  cluster = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 50 });
  map.addLayer(cluster);
}
async function loadParks() {
  const parks = await j('/parks');
  const markers = [];
  for (const p of parks) {
    if (p.lat == null || p.lon == null) continue;
    const m = L.circleMarker([p.lat, p.lon], { radius: 5, color: '#2a6b3b', weight: 1,
      fillColor: '#4caf6e', fillOpacity: .85 });
    m.on('click', () => openPark(p.id));
    m.bindTooltip(p.name_ja, { direction: 'top' });
    markers.push(m);
  }
  cluster.addLayers(markers);
}

// ---- park panel -------------------------------------------------------------
async function openPark(id) {
  $('panel').innerHTML = '<div class="placeholder">…</div>';
  const p = await j('/parks/' + id);
  curPark = p;
  renderPark();
  if (window.matchMedia('(max-width: 760px)').matches) $('panel').scrollIntoView({ behavior: 'smooth' });
}
function renderPark() {
  const p = curPark; if (!p) return;
  const U = UI[lang];
  const name = (lang === 'ja' ? p.name_ja : (p.name_en || p.name_ja)) || p.name_ja;
  const meta = [];
  meta.push(`${p.species.length} ${U.species}`);
  if (p.has_parking === 1 || p.has_parking === 0) meta.push(U.parking[p.has_parking]);
  if (p.official_url) meta.push(`<a href="${esc(p.official_url)}" target="_blank" rel="noopener">${U.official}</a>`);
  // group species
  const byGrp = {};
  for (const s of p.species) (byGrp[s.group || 'unclassified'] ||= []).push(s);
  const order = ['plant','bird','insect','mammal','herp','fish','mollusk','crustacean',
                 'arachnid_myriapod','mushroom','small_aquatic','other_animal','unclassified'];
  const groups = Object.keys(byGrp).sort((a,b) => (order.indexOf(a)+1||99) - (order.indexOf(b)+1||99));
  let html = `<div class="park-name">${esc(name)}</div><div class="park-meta">${meta.join(' · ')}</div>`;
  for (const g of groups) {
    html += `<div class="grp-h">${grpLabel(g)} <span class="count">(${byGrp[g].length})</span></div><div class="grid">`;
    for (const s of byGrp[g]) {
      const bg = s.p ? `background-image:url('${esc(s.p)}')` : '';
      html += `<div class="card" onclick="App.openSpecies(${s.id})"><div class="ph" style="${bg}"></div>`
            + `<div class="nm"><b>${esc(dispName(s))}</b><i>${esc(s.sci || '')}</i></div></div>`;
    }
    html += '</div>';
  }
  $('panel').innerHTML = html;
}

// ---- species modal ----------------------------------------------------------
async function openSpecies(id) {
  const s = await j('/species/' + id);
  modalSpecies = s; photoIdx = 0;
  renderModal();
  $('modal').classList.add('on');
}
function renderModal() {
  const s = modalSpecies; if (!s) return;
  const U = UI[lang];
  const imgs = s.imgs || [];
  const cur = imgs[photoIdx];
  let ph = '';
  if (cur) {
    const [url, attr, src] = cur;
    const nav = imgs.length > 1
      ? `<button class="nav l" onclick="App.photo(-1)">‹</button><button class="nav r" onclick="App.photo(1)">›</button>` : '';
    const a = attr ? `<div class="attr">${src ? `<a href="${esc(src)}" target="_blank" rel="noopener">${esc(attr)}</a>` : esc(attr)}</div>` : '';
    ph = `<div style="position:absolute;inset:0;background:#222 url('${esc(url)}') center/contain no-repeat"></div>${nav}${a}`;
  } else if (s.p) {
    ph = `<div style="position:absolute;inset:0;background:#222 url('${esc(s.p)}') center/contain no-repeat"></div>`;
  }
  $('mphoto').innerHTML = ph;

  const pr = (s.pr && (s.pr[PROFILE_LANG[lang]] || s.pr.en || s.pr.ja)) || null;
  const alt = [];
  if (lang !== 'ja' && s.ja) alt.push(s.ja);
  if (lang !== 'zh' && s.zh) alt.push(s.zh);
  if (lang !== 'en' && s.en) alt.push(s.en);
  let body = `<h2>${esc(dispName(s))}</h2><div class="sci">${esc(s.sci || '')}</div>`;
  body += `<div class="alt">${esc(alt.join(' · '))}</div>`;
  body += `<div><span class="pill">${grpLabel(s.group)}</span></div>`;
  if (pr) {
    if (pr.summary)      body += `<div class="sec"><b>${U.summary}</b>${esc(pr.summary)}</div>`;
    if (pr.habitat_hint) body += `<div class="sec"><b>${U.habitat}</b>${esc(pr.habitat_hint)}</div>`;
    if (pr.finding_tips) body += `<div class="sec"><b>${U.tips}</b>${esc(pr.finding_tips)}</div>`;
  }
  $('mbody').innerHTML = body;
}
function photo(d) {
  const n = (modalSpecies.imgs || []).length; if (!n) return;
  photoIdx = (photoIdx + d + n) % n; renderModal();
}
function closeModal() { $('modal').classList.remove('on'); modalSpecies = null; }

// ---- search -----------------------------------------------------------------
let searchTimer = null;
function onSearch(e) {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (q.length < 2) return;
  searchTimer = setTimeout(async () => {
    const res = await j('/search?q=' + encodeURIComponent(q) + '&limit=24');
    let html = `<div class="park-name">🔍 ${esc(q)}</div><div class="park-meta">${res.length} ${UI[lang].species}</div><div class="grid">`;
    for (const s of res) {
      const bg = s.p ? `background-image:url('${esc(s.p)}')` : '';
      html += `<div class="card" onclick="App.openSpecies(${s.id})"><div class="ph" style="${bg}"></div>`
            + `<div class="nm"><b>${esc(dispName(s))}</b><i>${esc(s.sci || '')}</i></div></div>`;
    }
    html += '</div>';
    $('panel').innerHTML = html;
  }, 280);
}

// ---- chrome -----------------------------------------------------------------
function setLang(l) {
  lang = l; localStorage.setItem('pl_lang', l);
  document.documentElement.lang = l === 'zhT' ? 'zh-Hant' : l;
  renderChrome();
  if (modalSpecies) renderModal();
  if (curPark) renderPark(); else $('ph').innerHTML = UI[lang].placeholder;
}
function renderChrome() {
  $('tagline').textContent = UI[lang].tagline;
  $('search').placeholder = UI[lang].srch;
  $('lang').innerHTML = LANGS.map(l =>
    `<button class="${l === lang ? 'on' : ''}" onclick="App.setLang('${l}')">${LANG_LABEL[l]}</button>`).join('');
}

const App = { openPark, openSpecies, setLang, closeModal, photo };
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
  initMap();
  loadParks().catch(err => { $('ph').innerHTML = 'load error: ' + esc(err.message); });
})();
