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
const dataMeta = () => getJSON(DATA + '/meta.json');
const dataSeason = (m) => getJSON(DATA + '/season/' + m + '.json');
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
let _searchMap = null;  // id -> species card object, built once from the search index
async function searchMap() {
  if (!_searchIdx) _searchIdx = await getJSON(DATA + '/search-index.json');
  if (!_searchMap) {
    _searchMap = new Map();
    for (const r of _searchIdx)  // [id, sci, ja, en, zh, zhT, group, p, np]
      _searchMap.set(r[0], { id: r[0], sci: r[1], ja: r[2], en: r[3], zh: r[4], zhT: r[5], group: r[6], p: r[7] });
  }
  return _searchMap;
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
    regional:n=>`周辺地域の記録も表示 (+${n})`, regionalBadge:m=>`📍${m} 地域`, regionalNote:'この地域（市区町村）で記録あり・園内確認ではありません',
    showMore:n=>`さらに ${n} 種を表示`, showAll:n=>`残り ${n} 種をすべて表示`,
    viewOnMap:'この種が見られる公園を地図で表示', mapFiltered:(name,n)=>`📍 ${name} が見られる ${n} 公園`, showAllParks:'すべての公園に戻る', locate:'現在地に移動',
    nearMe:'📍 近くの公園', nearHeader:(n)=>`近くの公園 ${n} 件`, nearBusy:'現在地を取得中…',
    nearNone:'この付近に公園が見つかりませんでした', geoDenied:'位置情報を取得できませんでした（ブラウザの位置情報を許可してください）',
    seasonNow:'🌸 今が見ごろ', seasonHeader:(mn,n)=>`${mn}に見られる ${n} 種`,
    nearShort:'📍 近く', seasonShort:'🌸 見ごろ', allGroups:'すべて' },
  en: { tagline:'A map of life in Japanese parks', placeholder:'🗺 Click a park marker on the map<br>or use the search box above',
    species:'species', parking:{1:'🅿️ Parking',0:'🚫 No parking'}, official:'Official site ↗',
    summary:'About', habitat:'Habitat', tips:'How to find', season:'Recorded months', srch:'Search species / park',
    seasonUnknown:'Year-round / unknown', parksWith:'Parks where this species occurs',
    sort:'Sort', sortFreq:'Record count (high→low)', sortName:'Name', sortSci:'Scientific A→Z',
    month:'Month', monthAll:'All', parkingOnly:'🅿️ Parking only', inPark:'Photos at this park', matched:n=>`${n} species matched`,
    regional:n=>`Show nearby regional records (+${n})`, regionalBadge:m=>`📍${m} region`, regionalNote:'Recorded in this municipality — not confirmed inside the park',
    showMore:n=>`Show ${n} more`, showAll:n=>`Show all ${n} remaining`,
    viewOnMap:'Show parks with this species on the map', mapFiltered:(name,n)=>`📍 ${n} parks with ${name}`, showAllParks:'Back to all parks', locate:'My location',
    nearMe:'📍 Parks near me', nearHeader:(n)=>`${n} parks near you`, nearBusy:'Finding your location…',
    nearNone:'No parks found nearby', geoDenied:'Couldn’t get your location (allow location access in your browser)',
    seasonNow:'🌸 In season now', seasonHeader:(mn,n)=>`${n} species in season · ${mn}`,
    nearShort:'📍 Near me', seasonShort:'🌸 In season', allGroups:'All' },
  zh: { tagline:'日本公园的生物地图', placeholder:'🗺 点击地图上的公园标记<br>或使用上方搜索框',
    species:'种', parking:{1:'🅿️ 有停车场',0:'🚫 无停车场'}, official:'官方网站 ↗',
    summary:'简介', habitat:'栖息环境', tips:'观察提示', season:'记录月份', srch:'搜索物种 / 公园',
    seasonUnknown:'全年／不明', parksWith:'可见到该物种的公园',
    sort:'排序', sortFreq:'记录数（多→少）', sortName:'名称', sortSci:'学名 A→Z',
    month:'月份', monthAll:'全部', parkingOnly:'🅿️ 仅有停车场', inPark:'本公园实拍', matched:n=>`共 ${n} 种符合`,
    regional:n=>`含周边区域记录 (+${n})`, regionalBadge:m=>`📍${m} 区域`, regionalNote:'该市区町村有记录 · 非园内确认',
    showMore:n=>`再显示 ${n} 种`, showAll:n=>`显示剩余全部 ${n} 种`,
    viewOnMap:'在地图上显示有该物种的公园', mapFiltered:(name,n)=>`📍 ${n} 个公园有 ${name}`, showAllParks:'返回全部公园', locate:'我的位置',
    nearMe:'📍 附近的公园', nearHeader:(n)=>`附近 ${n} 个公园`, nearBusy:'正在获取你的位置…',
    nearNone:'附近未找到公园', geoDenied:'无法获取你的位置（请在浏览器中允许定位）',
    seasonNow:'🌸 本月当季', seasonHeader:(mn,n)=>`${mn}当季 ${n} 种`,
    nearShort:'📍 附近', seasonShort:'🌸 当季', allGroups:'全部' },
  zhT: { tagline:'日本公園的生物地圖', placeholder:'🗺 點擊地圖上的公園標記<br>或使用上方搜尋框',
    species:'種', parking:{1:'🅿️ 有停車場',0:'🚫 無停車場'}, official:'官方網站 ↗',
    summary:'簡介', habitat:'棲息環境', tips:'觀察提示', season:'記錄月份', srch:'搜尋物種 / 公園',
    seasonUnknown:'全年／不明', parksWith:'可見到該物種的公園',
    sort:'排序', sortFreq:'記錄數（多→少）', sortName:'名稱', sortSci:'學名 A→Z',
    month:'月份', monthAll:'全部', parkingOnly:'🅿️ 僅有停車場', inPark:'本公園實拍', matched:n=>`共 ${n} 種符合`,
    regional:n=>`含周邊區域記錄 (+${n})`, regionalBadge:m=>`📍${m} 區域`, regionalNote:'該市區町村有記錄 · 非園內確認',
    showMore:n=>`再顯示 ${n} 種`, showAll:n=>`顯示剩餘全部 ${n} 種`,
    viewOnMap:'在地圖上顯示有該物種的公園', mapFiltered:(name,n)=>`📍 ${n} 個公園有 ${name}`, showAllParks:'返回全部公園', locate:'我的位置',
    nearMe:'📍 附近的公園', nearHeader:(n)=>`附近 ${n} 個公園`, nearBusy:'正在取得你的位置…',
    nearNone:'附近未找到公園', geoDenied:'無法取得你的位置（請在瀏覽器中允許定位）',
    seasonNow:'🌸 本月當季', seasonHeader:(mn,n)=>`${mn}當季 ${n} 種`,
    nearShort:'📍 附近', seasonShort:'🌸 當季', allGroups:'全部' },
};
const PROFILE_LANG = { ja:'ja', en:'en', zh:'zh', zhT:'zhT' };  // species_profile.lang keys

// ---- credits / data-source attribution --------------------------------------
const FEEDBACK_URL = 'https://github.com/paranoid2droid/parklife/issues';
// Source names/URLs are language-neutral; only headings/prose are translated.
// Each item: {name?, url?, lic?, prov}. Without `name`, the translated
// provides-label is used as the primary text (e.g. the park official sites row).
const SOURCE_GROUPS = [
  { sec:'secOcc', items:[
    { name:'iNaturalist', url:'https://www.inaturalist.org', lic:'CC0 · CC BY · CC BY-NC', prov:'occ' },
    { name:'GBIF', url:'https://www.gbif.org', lic:'CC BY · CC0', prov:'occ' },
    { name:'eBird · Cornell Lab of Ornithology', url:'https://ebird.org', lic:'CC BY-NC', prov:'occ' },
  ]},
  { sec:'secPhoto', items:[
    { name:'iNaturalist', url:'https://www.inaturalist.org', lic:'CC0 · CC BY · CC BY-NC · CC BY-SA', prov:'photo' },
    { name:'Wikimedia Commons', url:'https://commons.wikimedia.org', lic:'CC · Public Domain', prov:'photo' },
    { name:'GBIF', url:'https://www.gbif.org', lic:'CC', prov:'photo' },
  ]},
  { sec:'secName', items:[
    { name:'Wikipedia (日本語)', url:'https://ja.wikipedia.org', lic:'CC BY-SA', prov:'name' },
    { name:'Catalogue of Life', url:'https://www.catalogueoflife.org', lic:'CC BY', prov:'name' },
    { name:'GBIF Backbone Taxonomy', url:'https://www.gbif.org', lic:'CC BY', prov:'name' },
  ]},
  { sec:'secPark', items:[
    { name:'国土数値情報 都市公園データ · 国土交通省 (MLIT)', url:'https://nlftp.mlit.go.jp/ksj/', lic:'政府標準利用規約', prov:'park' },
    { prov:'web' },
    { name:'OpenStreetMap', url:'https://www.openstreetmap.org/copyright', lic:'ODbL', prov:'map' },
    { name:'Nominatim · OpenStreetMap', url:'https://nominatim.org', lic:'ODbL', prov:'geo' },
  ]},
];
const ABOUT = {
  ja: { sub:'公園の生きもの地図',
    lead:'日本全国の公園で記録された植物・動物・菌類を、公園ごと・季節ごとに調べられる地図です。iNaturalist・GBIF・eBird などの観察データと、各公園の公式情報を統合しています。',
    howTitle:'使い方',
    how:['地図の公園マーカーをクリックすると、その公園の生きもの一覧が開きます',
      '上の検索ボックスで種名・公園名を検索できます',
      '種をクリックすると写真・解説・見られる季節・分布する公園が見られます',
      '右上のボタンで 日本語・English・简・繁 を切り替えられます'],
    stat:(p,s)=>`${p} 公園 · ${s} 種を収録`, upd:(d)=>`最終更新: ${d}`,
    creditsLink:'データ出典・クレジット →', start:'はじめる',
    install:'📲 アプリをインストール', installHint:'共有メニューから「ホーム画面に追加」でアプリとして使えます' },
  en: { sub:"A map of life in Japan's parks",
    lead:'Explore the plants, animals and fungi recorded in parks across Japan — by park and by season. It combines observation data from iNaturalist, GBIF and eBird with each park’s official information.',
    howTitle:'How to use',
    how:['Click a park marker on the map to open that park’s species list',
      'Search a species or park name in the box above',
      'Click a species for photos, a description, its season, and the parks where it occurs',
      'Switch between 日本語 / English / 简 / 繁 with the top-right buttons'],
    stat:(p,s)=>`${p} parks · ${s} species`, upd:(d)=>`Last updated: ${d}`,
    creditsLink:'Data sources & credits →', start:'Get started',
    install:'📲 Install app', installHint:'Tap Share → “Add to Home Screen” to install' },
  zh: { sub:'日本公园的生物地图',
    lead:'探索日本各地公园记录到的植物、动物与菌类——按公园、按季节查询。整合了 iNaturalist、GBIF、eBird 的观察数据与各公园的官方信息。',
    howTitle:'使用方法',
    how:['点击地图上的公园标记，查看该公园的物种列表',
      '在上方搜索框搜索物种名或公园名',
      '点击物种可查看照片、简介、出现季节及分布的公园',
      '右上角按钮可切换 日本語 / English / 简 / 繁'],
    stat:(p,s)=>`收录 ${p} 个公园 · ${s} 种`, upd:(d)=>`最后更新：${d}`,
    creditsLink:'数据来源与致谢 →', start:'开始使用',
    install:'📲 安装应用', installHint:'点击分享 →「添加到主屏幕」即可作为应用使用' },
  zhT: { sub:'日本公園的生物地圖',
    lead:'探索日本各地公園記錄到的植物、動物與菌類——按公園、按季節查詢。整合了 iNaturalist、GBIF、eBird 的觀察資料與各公園的官方資訊。',
    howTitle:'使用方法',
    how:['點擊地圖上的公園標記，查看該公園的物種列表',
      '在上方搜尋框搜尋物種名或公園名',
      '點擊物種可查看照片、簡介、出現季節及分布的公園',
      '右上角按鈕可切換 日本語 / English / 简 / 繁'],
    stat:(p,s)=>`收錄 ${p} 個公園 · ${s} 種`, upd:(d)=>`最後更新：${d}`,
    creditsLink:'資料來源與致謝 →', start:'開始使用',
    install:'📲 安裝應用', installHint:'點擊分享 →「加入主畫面」即可作為應用使用' },
};
const CREDITS = {
  ja: { title:'データ出典・クレジット', close:'閉じる',
    intro:'「パークライフ」は公開されているオープンデータを組み合わせた非営利プロジェクトです。主なデータ出典とライセンスは次のとおりです。',
    secOcc:'生きもの観察データ', secPhoto:'写真', secName:'名前・分類', secPark:'公園・地図データ',
    photoNote:'各写真には撮影者とライセンスを表示しています。写真の著作権は各撮影者に帰属し、記載のクリエイティブ・コモンズ条件のもとで利用しています。',
    feedback:'誤りの報告・ご意見', feedbackLink:'GitHub Issues で報告',
    disclaimer:'本サイトは非営利の個人プロジェクトであり、掲載する公園やデータ提供元とは関係ありません。データは現状有姿（無保証）で提供されます。',
    provides:{ occ:'観察記録', photo:'写真', name:'和名・学名・分類', park:'公園一覧・面積・区域',
      map:'地図・駐車場', geo:'座標（ジオコーディング）', web:'各公園の公式サイト（東京都・神奈川県・千葉県・埼玉県 ほか）' } },
  en: { title:'Data sources & credits', close:'Close',
    intro:'Parklife is a non-commercial project built from publicly available open data. The main sources and licenses are listed below.',
    secOcc:'Species occurrence data', secPhoto:'Photos', secName:'Names & taxonomy', secPark:'Park & map data',
    photoNote:'Each photo shows its photographer and license. Photos remain © their photographers and are used under the stated Creative Commons terms.',
    feedback:'Report an error / feedback', feedbackLink:'Report on GitHub Issues',
    disclaimer:'This is a non-commercial personal project and is not affiliated with the parks or data providers shown. Data is provided “as is”, without warranty.',
    provides:{ occ:'occurrence records', photo:'photos', name:'names & taxonomy', park:'park list, area & boundary',
      map:'map & parking', geo:'coordinates (geocoding)', web:'park official sites (Tokyo, Kanagawa, Chiba, Saitama, etc.)' } },
  zh: { title:'数据来源与致谢', close:'关闭',
    intro:'「Parklife」是基于公开开放数据构建的非营利项目。主要数据来源与许可如下。',
    secOcc:'生物观察数据', secPhoto:'照片', secName:'名称与分类', secPark:'公园与地图数据',
    photoNote:'每张照片都会显示拍摄者与许可协议。照片版权归各拍摄者所有，依据所标注的知识共享（CC）条款使用。',
    feedback:'报告错误 / 反馈', feedbackLink:'在 GitHub Issues 反馈',
    disclaimer:'本站为非营利个人项目，与所列公园及数据提供方无关。数据按“现状”提供，不作任何担保。',
    provides:{ occ:'观察记录', photo:'照片', name:'名称与分类', park:'公园列表・面积・范围',
      map:'地图与停车场', geo:'坐标（地理编码）', web:'各公园官方网站（东京都・神奈川县・千叶县・埼玉县 等）' } },
  zhT: { title:'資料來源與致謝', close:'關閉',
    intro:'「Parklife」是基於公開開放資料建構的非營利專案。主要資料來源與授權如下。',
    secOcc:'生物觀察資料', secPhoto:'照片', secName:'名稱與分類', secPark:'公園與地圖資料',
    photoNote:'每張照片都會顯示拍攝者與授權條款。照片版權歸各拍攝者所有，依所標註的創用 CC 條款使用。',
    feedback:'回報錯誤 / 意見', feedbackLink:'於 GitHub Issues 回報',
    disclaimer:'本站為非營利個人專案，與所列公園及資料提供方無關。資料按「現狀」提供，不作任何擔保。',
    provides:{ occ:'觀察記錄', photo:'照片', name:'名稱與分類', park:'公園列表・面積・範圍',
      map:'地圖與停車場', geo:'座標（地理編碼）', web:'各公園官方網站（東京都・神奈川縣・千葉縣・埼玉縣 等）' } },
};

// ---- state ------------------------------------------------------------------
let lang = localStorage.getItem('pl_lang') || (navigator.language || 'ja').slice(0,2);
if (!LANGS.includes(lang)) lang = lang.startsWith('zh') ? 'zh' : (lang === 'ja' ? 'ja' : 'en');
let curPark = null;       // last loaded park detail
let modalSpecies = null;  // species detail in modal
let modalImgs = [];       // combined gallery shown in modal (park-local + species hero)
let photoIdx = 0;
let sortMode = localStorage.getItem('pl_sort') || 'freq';  // freq | name | sci
let monthFilter = 0;      // 0 = all; 1..12 = that month (soft filter)
let showRegional = localStorage.getItem('pl_regional') === '1';  // include 'admin:municipality' (a:1) cards
let hiddenGroups = new Set();
let parkingOnly = false;
let allParks = [];        // cached light park index for the map filter
let groupShown = {};      // group -> how many cards currently expanded (pagination)
const GROUP_CAP = 48;     // initial cards per group before "show more"
let speciesFilter = null; // {ids:Set<parkId>, name} when showing one species' parks on the map
let userLayer = null;     // Leaflet layer for the user's location dot + accuracy circle
let locateControl = null; // the "my location" map button
let locating = false;     // guard against overlapping geolocation requests
let deferredPrompt = null; // captured beforeinstallprompt event (Android/Chrome PWA install)

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
function nearestParks(lat, lon, n = 12) {
  const withKm = [];
  for (const p of allParks) {
    if (p.lat == null || p.lon == null) continue;
    withKm.push({ park: p, km: distanceKm(lat, lon, p.lat, p.lon) });
  }
  withKm.sort((a, b) => a.km - b.km);
  return withKm.slice(0, n);
}
const fmtKm = (km) => (km < 10 ? km.toFixed(1) : Math.round(km).toString()) + ' km';
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
// ---- discovery: parks near me -----------------------------------------------
function renderEmpty() {
  inSeasonView = false;
  $('panel').innerHTML =
    `<div class="placeholder" id="ph">${UI[lang].placeholder}`
    + `<div class="near-cta">`
    + `<button class="near-btn" onclick="App.discoverNearby()">${esc(UI[lang].nearMe)}</button> `
    + `<button class="near-btn alt" onclick="App.discoverSeason()">${esc(UI[lang].seasonNow)}</button>`
    + `</div></div>`;
}
function discoverNearby() {
  if (locating) return;
  const U = UI[lang];
  inSeasonView = false; curPark = null; speciesFilter = null; setHash('', false);
  $('panel').innerHTML = `<div class="placeholder">${esc(U.nearBusy)}</div>`;
  locating = true; setLocateState('busy');
  geolocate(
    (lat, lon, acc) => {
      locating = false; setLocateState('');
      showUserLocation(lat, lon, acc);
      map.setView([lat, lon], 11);
      renderNearby(nearestParks(lat, lon, 12));
    },
    () => {
      locating = false; setLocateState('err');
      $('panel').innerHTML = `<div class="placeholder">${esc(U.geoDenied)}`
        + `<div class="near-cta"><button class="near-btn" onclick="App.discoverNearby()">${esc(U.nearMe)}</button></div></div>`;
    });
}
function renderNearby(list) {
  const U = UI[lang];
  if (!list.length) { $('panel').innerHTML = `<div class="placeholder">${esc(U.nearNone)}</div>`; return; }
  const rows = list.map(({ park: p, km }) => {
    const name = (lang === 'ja' ? p.name_ja : (p.name_en || p.name_ja)) || p.name_ja;
    const pk = p.has_parking === 1 ? `<span class="near-pk">${esc(U.parking[1])}</span>` : '';
    return `<div class="near-item" onclick="App.openPark(${p.id})">`
      + `<div class="near-nm">${esc(name)}${pk}</div>`
      + `<div class="near-km">${esc(fmtKm(km))}</div></div>`;
  }).join('');
  $('panel').innerHTML = `<div class="park-name">📍 ${esc(U.nearHeader(list.length))}</div>`
    + `<div class="near-list">${rows}</div>`;
}

// ---- discovery: in season this month ----------------------------------------
const SEASON_GROUP_CAP = 24;
let seasonMonth = 0, seasonRanked = [], inSeasonView = false;
let seasonGroups = null;      // Set of enabled taxon groups (null before first load)
let seasonGroupShown = {};    // per-group card cap
async function discoverSeason(month) {
  seasonMonth = month || (new Date().getMonth() + 1);  // auto-load the current month
  inSeasonView = true; curPark = null; speciesFilter = null; setHash('', false);
  $('panel').innerHTML = '<div class="placeholder">…</div>';
  const [rows, map] = await Promise.all([dataSeason(seasonMonth), searchMap()]);
  seasonRanked = rows.map(([id]) => map.get(id)).filter(Boolean);  // global rank order preserved
  seasonGroups = new Set(seasonGroupsPresent().map(([g]) => g));   // default: all groups checked
  seasonGroupShown = {};
  renderSeason();
}
function seasonGroupsPresent() {
  const m = new Map();
  for (const s of seasonRanked) { const g = s.group || 'unclassified'; m.set(g, (m.get(g) || 0) + 1); }
  return [...m.entries()].sort((a, b) =>
    (GROUP_ORDER.indexOf(a[0]) + 1 || 99) - (GROUP_ORDER.indexOf(b[0]) + 1 || 99));
}
function renderSeason() {
  const U = UI[lang];
  const present = seasonGroupsPresent();
  const opts = MONTHS[lang].map((nm, i) =>
    `<option value="${i + 1}"${i + 1 === seasonMonth ? ' selected' : ''}>${esc(nm)}</option>`).join('');
  const allOn = present.every(([g]) => seasonGroups.has(g));
  const chips = `<label class="gcb all"><input type="checkbox"${allOn ? ' checked' : ''} `
      + `onchange="App.toggleSeasonAll(this.checked)"> ${esc(U.allGroups)}</label>`
    + present.map(([g, c]) => `<label class="gcb"><input type="checkbox"${seasonGroups.has(g) ? ' checked' : ''} `
      + `onchange="App.toggleSeasonGroup('${g}')"> ${grpLabel(g)} <span class="count">${c}</span></label>`).join('');
  let body = '';
  for (const [g, c] of present) {
    if (!seasonGroups.has(g)) continue;
    const list = seasonRanked.filter(s => (s.group || 'unclassified') === g);  // rank-ordered
    const cap = seasonGroupShown[g] || SEASON_GROUP_CAP;
    body += `<div class="grp-h static">${grpLabel(g)} <span class="count">(${c})</span></div>`
      + `<div class="grid">${list.slice(0, cap).map(speciesCard).join('')}</div>`;
    const rest = list.length - cap;
    if (rest > 0) {
      const step = Math.min(rest, 48);
      body += `<button class="more-btn" onclick="App.seasonMore('${g}',${step})">${esc(U.showMore(step))}</button>`;
      if (rest > step) body += `<button class="more-btn" onclick="App.seasonMore('${g}',${rest})">${esc(U.showAll(rest))}</button>`;
    }
  }
  $('panel').innerHTML =
    `<div class="park-name">🌸 ${esc(U.seasonHeader(MONTHS[lang][seasonMonth - 1], seasonRanked.length))}</div>`
    + `<div class="controls"><span>${esc(U.month)}: `
    + `<select onchange="App.discoverSeason(+this.value)">${opts}</select></span></div>`
    + `<div class="grp-filter">${chips}</div>`
    + body;
}
function seasonMore(g, n) { seasonGroupShown[g] = (seasonGroupShown[g] || SEASON_GROUP_CAP) + n; renderSeason(); }
function toggleSeasonGroup(g) { seasonGroups.has(g) ? seasonGroups.delete(g) : seasonGroups.add(g); renderSeason(); }
function toggleSeasonAll(on) {
  seasonGroups = on ? new Set(seasonGroupsPresent().map(([g]) => g)) : new Set();
  renderSeason();
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
  inSeasonView = false;
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
  // 'a' = regional (市区町村) record, not confirmed on-site: badge it with the muni.
  const badge = (s.a && curPark && curPark.municipality)
    ? `<span class="reg-badge" title="${esc(UI[lang].regionalNote)}">${esc(UI[lang].regionalBadge(curPark.municipality))}</span>` : '';
  return `<div class="card${s.a ? ' regional' : ''}" onclick="App.openSpecies(${s.id},${curPark ? curPark.id : 'null'})">`
       + `<div class="ph" style="${bg}"></div>`
       + `<div class="nm"><b>${esc(dispName(s))}</b><i>${esc(s.sci || '')}</i>${badge}</div></div>`;
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

  const regionalCount = p.species.reduce((n, s) => n + (s.a ? 1 : 0), 0);
  const shown = p.species.filter(s => passMonth(s) && (showRegional || !s.a));
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
    + (regionalCount ? `<label class="reg-toggle" title="${esc(U.regionalNote)}">`
        + `<input type="checkbox"${showRegional ? ' checked' : ''} onchange="App.setRegional(this.checked)"> ${U.regional(regionalCount)}</label>` : '')
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
function setRegional(on) { showRegional = !!on; localStorage.setItem('pl_regional', on ? '1' : '0'); groupShown = {}; renderPark(); }
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
    inSeasonView = false; curPark = null;  // search context: cards open without a park
    let html = `<div class="park-name">🔍 ${esc(q)}</div><div class="park-meta">${res.length} ${UI[lang].species}</div><div class="grid">`;
    html += res.map(speciesCard).join('');
    html += '</div>';
    $('panel').innerHTML = html;
  }, 280);
}

// ---- about / landing --------------------------------------------------------
let _meta = null;  // {parks, species, generated} cached after first About open
function renderAbout() {
  const a = ABOUT[lang];
  const nf = (n) => n == null ? '—' : n.toLocaleString(lang === 'ja' ? 'ja-JP' : 'en-US');
  let statLine = '';
  if (_meta) {
    const d = _meta.generated
      ? new Date(_meta.generated * 1000).toISOString().slice(0, 10) : null;
    statLine = `<div class="stat">${esc(a.stat(nf(_meta.parks), nf(_meta.species)))}`
      + (d ? ` <span class="upd">· ${esc(a.upd(d))}</span>` : '') + `</div>`;
  }
  $('abody').innerHTML =
    `<h2>🌿 Parklife</h2><p class="sub">${esc(a.sub)}</p>`
    + `<p class="lead">${esc(a.lead)}</p>`
    + statLine
    + `<h3>${esc(a.howTitle)}</h3><ol>${a.how.map(s => `<li>${esc(s)}</li>`).join('')}</ol>`
    + `<p class="credits-link"><a onclick="App.closeAbout();App.openCredits()">${esc(a.creditsLink)}</a></p>`
    + installMarkup(a)
    + `<button class="start-btn" onclick="App.closeAbout()">${esc(a.start)}</button>`;
}
const isStandalone = () =>
  matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
function installMarkup(a) {
  if (isStandalone()) return '';                       // already installed
  if (deferredPrompt)                                  // Android/Chrome: real prompt
    return `<p class="fb"><button class="near-btn" onclick="App.installApp()">${esc(a.install)}</button></p>`;
  if (/iphone|ipad|ipod/i.test(navigator.userAgent))   // iOS Safari: manual A2HS hint
    return `<p class="note">${esc(a.installHint)}</p>`;
  return '';
}
function installApp() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  deferredPrompt.userChoice.finally(() => { deferredPrompt = null; renderAbout(); });
}
function openAbout() {
  renderAbout();
  $('about').classList.add('on');
  if (!_meta) dataMeta().then(m => { _meta = m; if ($('about').classList.contains('on')) renderAbout(); }).catch(() => {});
}
function closeAbout() {
  $('about').classList.remove('on');
  try { localStorage.setItem('pl_seen_about', '1'); } catch {}
}

// ---- credits ----------------------------------------------------------------
function renderCredits() {
  const c = CREDITS[lang];
  let h = `<h2>${esc(c.title)}</h2><p class="intro">${esc(c.intro)}</p>`;
  for (const g of SOURCE_GROUPS) {
    h += `<h3>${esc(c[g.sec])}</h3><ul>`;
    for (const it of g.items) {
      const label = it.name || c.provides[it.prov];
      const primary = it.url
        ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(label)}</a>` : esc(label);
      const prov = it.name ? ` <span class="prov">— ${esc(c.provides[it.prov])}</span>` : '';
      const lic = it.lic ? `<span class="lic">${esc(it.lic)}</span>` : '';
      h += `<li>${primary}${prov}${lic}</li>`;
    }
    h += '</ul>';
    if (g.sec === 'secPhoto') h += `<p class="note">${esc(c.photoNote)}</p>`;
  }
  h += `<p class="fb">${esc(c.feedback)}: `
     + `<a href="${FEEDBACK_URL}" target="_blank" rel="noopener">${esc(c.feedbackLink)}</a></p>`;
  h += `<p class="disc">${esc(c.disclaimer)}</p>`;
  $('cbody').innerHTML = h;
}
function openCredits() { renderCredits(); $('credits').classList.add('on'); }
function closeCredits() { $('credits').classList.remove('on'); }

// ---- chrome -----------------------------------------------------------------
function setLang(l) {
  lang = l; localStorage.setItem('pl_lang', l);
  document.documentElement.lang = l === 'zhT' ? 'zh-Hant' : l;
  renderChrome();
  if (map) addParkingControl();  // its label is language-dependent
  { const lb = $('locateBtn'); if (lb) { lb.title = UI[lang].locate; lb.setAttribute('aria-label', UI[lang].locate); } }
  if (modalSpecies) renderModal();
  if ($('about').classList.contains('on')) renderAbout();
  if ($('credits').classList.contains('on')) renderCredits();
  if (curPark) renderPark(); else if (inSeasonView) renderSeason(); else if ($('ph')) renderEmpty();
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
  { const cb = $('creditsBtn'); if (cb) { cb.title = CREDITS[lang].title; cb.setAttribute('aria-label', CREDITS[lang].title); } }
  { const br = $('brand'); if (br) br.title = ABOUT[lang].sub; }
  { const nb = $('nearBtn'); if (nb) { nb.textContent = UI[lang].nearShort; nb.title = UI[lang].nearMe; nb.setAttribute('aria-label', UI[lang].nearMe); } }
  { const sb = $('seasonBtn'); if (sb) { sb.textContent = UI[lang].seasonShort; sb.title = UI[lang].seasonNow; sb.setAttribute('aria-label', UI[lang].seasonNow); } }
}

const App = { openPark, openSpecies, setLang, closeModal, photo, setSort, setMonth, setRegional, toggleGroup, showMore,
              viewSpeciesOnMap, clearSpeciesFilter, openCredits, closeCredits, openAbout, closeAbout,
              discoverNearby, discoverSeason, seasonMore, toggleSeasonGroup, toggleSeasonAll, installApp };
window.App = App;

(function main() {
  renderChrome();
  renderEmpty();
  $('search').addEventListener('input', onSearch);
  $('modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
  $('credits').addEventListener('click', e => { if (e.target.id === 'credits') closeCredits(); });
  $('about').addEventListener('click', e => { if (e.target.id === 'about') closeAbout(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeModal(); closeCredits(); closeAbout(); }
    if (modalSpecies && e.key === 'ArrowLeft') photo(-1);
    if (modalSpecies && e.key === 'ArrowRight') photo(1);
  });
  window.addEventListener('beforeinstallprompt', (e) => {  // stash for a custom install button
    e.preventDefault(); deferredPrompt = e;
    if ($('about').classList.contains('on')) renderAbout();
  });
  window.addEventListener('appinstalled', () => { deferredPrompt = null; });
  window.addEventListener('hashchange', applyHash);  // back/forward + manual edits (pushState doesn't fire this)
  initMap();
  loadParks()
    .then(() => {
      applyHash();
      if (!location.hash) {  // no shared link: auto-locate, and greet first-time visitors
        autoLocate();
        let seen; try { seen = localStorage.getItem('pl_seen_about'); } catch {}
        if (!seen) openAbout();
      }
    })
    .catch(err => { $('ph').innerHTML = 'load error: ' + esc(err.message); });
})();
