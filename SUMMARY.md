# parklife — current state

Generated: 2026-04-28 (single-session build)

## Where we stand

**209 公園 / 209 with data (100%) / 2,947 物种 / 48,833 観察記録**

| Prefecture | Parks (with data / total) | Observations |
|---|---|---|
| 東京都 (tokyo)        | 137 / 137 | 39,023 |
| 神奈川県 (kanagawa)  |  27 / 27  |  5,371 |
| 埼玉県 (saitama)     |  32 / 32  |  3,437 |
| 千葉県 (chiba)       |  13 / 13  |  1,002 |

| Taxon | Species | Observations | Notes |
|---|---|---|---|
| 🐛 昆虫類 | 1,593 | 26,187 | iNat + monthly seasonality |
| 🦜 鳥類   |   249 | 13,130 | iNat + per-park monthly bitmap |
| 🕷 クモ類 |   115 |  2,628 | iNat |
| 🌸 植物   |   423 |  1,615 | mainly TMG `花の見ごろ` |
| 🐟 魚類   |   155 |  1,418 | iNat (incl. shore observations) |
| 🦎 爬虫類 |    28 |  1,329 | |
| 🐚 軟体動物 | 177 |  1,198 | iNat |
| 🦌 哺乳類 |    42 |    576 | iNat + monthly |
| 🐸 両生類 |    19 |    420 | |
| 🌿 草本   |    57 |     99 | from official park lists |
| 🌳 樹木   |    26 |     75 | classified subset of plants |
| 🪴 灌木   |    24 |     71 | |
| 🍇 藤本   |     2 |     20 | |

## How the data was assembled

```
seed lists ──► fetch HTML ──► extract per-template ──► narrative scan
                                          │                  │
                                          ▼                  ▼
                                    Wikipedia ja  ─►  species + alias
                                          │
geocode (OSM) ─► iNaturalist species_counts (8 taxa) ─► observations
                                          │
                              monthly seasonality ──► months_bitmap
```

- Tokyo's TMG park association uses one CMS template across 137 parks → a single scraper covers them all.
- For non-Tokyo parks, the editorial-text scanner (Phase A/F) catches species mentioned by the park itself, while iNaturalist (Phase D) provides the bulk biodiversity data via lat/lon-radius queries.
- All species names are validated through Japanese Wikipedia's taxobox; 99% have a Japanese vernacular and a scientific name.

## Try the data

```bash
.venv/bin/python -m scripts.query stats
.venv/bin/python -m scripts.query bloom 5            # what's blooming/birding in May
.venv/bin/python -m scripts.query top --group bird   # most-widespread bird species
.venv/bin/python -m scripts.query diverse            # parks ranked by species diversity
.venv/bin/python -m scripts.query near 35.6586,139.7454 --radius_km 3
.venv/bin/python -m scripts.query park kasairinkai
.venv/bin/python -m scripts.query where ソメイヨシノ
```

Per-park markdown pages: `data/export/parks_md/<prefecture>/<slug>.md` plus `data/export/parks_md/INDEX.md`.

Single-file portable JSON: `data/export/parklife.json`.
NDJSON tuples (streaming): `data/export/park_species.ndjson`.

## Gaps & next steps

### What we now have (resolved earlier gaps)
- ✅ All 209 parks have data (manual coords for 17 sites Nominatim missed: Mt Takao, 小笠原, 八丈, 奥多摩, 大島, 小峰, etc.)
- ✅ Bird, insect, mammal months_bitmap all populated (3 × 12 monthly-iNaturalist passes, 6,912 API calls)

### Status
- ✅ Gap #6: dedup → `park_species` table (28,902 deduped pairs from 48,833 raw obs)
- ✅ Gap #8: photo URLs collected for 2,348 species (cached iNat data, no new API calls)
- ✅ Gap #1: animal seasonality (reptile / amphibian / fish / arachnid / mollusk monthly all done via launchd queue)
- ✅ Gap #2: cultivated plants done (captive=true Plantae)
- ✅ Gap #5: plant phenology done (iNat phenology histograms, place_id=6737)
- ✅ **Static HTML demo** deployed to `https://github.com/paranoid2droid/parklife-demo` (single-file Leaflet browser; updated via `scripts.deploy`)
- ⏳ **Parking info — partial (115 yes / 23 no / 71 unknown)**
  - Tried strict heading match → loose substring match. Reverted loose match because of false positives (group-only / advance-reservation parking shouldn't count as "available to public").
  - **TODO**: per-park manual review of the 71 unknown, or smarter classifier that distinguishes 一般来園者 vs 団体予約 parking. Park sites have varied phrasings.
- ❌ Gap #4: bird-zone PDFs evaluated; image-based or CMap-encoded → too fragile to parse beyond what pdfminer already catches. iNat already gives us the species these PDFs would. **Skipped.**
- 💤 Gap #3: 小笠原/八丈 newsletter depth — deprioritized (too far for practical outings).
- 💤 Gap #7: more prefectures — 1-2h each, on demand.
- 💤 Gap #9: time-of-day metadata — v2.
- 💤 Gap #10: eBird — needs API key.

### Autonomous queue (`data/run_queue.txt`)

`scripts/run_pending.py` consumes the queue under an fcntl lock. Each `pending:` line runs once; success flips to `done(...)`, failure to `failed(...)`. The runner loops within a single launchd firing until the queue is empty or it's been running 23 hours.

To enable launchd auto-resume across reboots:
```bash
cp /Users/zhe/ClaudeCode/parklife/com.parklife.queue.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.parklife.queue.plist
```

If a runner is already in flight (which it normally is right after a batch is queued), launchd firings just no-op until it finishes — that's intended.

### What v1 is "done enough" for
The current dataset can already drive: per-park biodiversity profiles, monthly bloom recommendations, "what bird/insect/etc. is in season near me", and a map-based outing planner. Anything beyond is depth, not breadth.

---

## TODO — 次回額度回復後 (recorded 2026-04-30)

1. **公園数を増やす**
   - 現状は **都立 / 県立** のみで 209 件。実際の関東公園はもっと多い:
     - 区立 / 市立 / 町立 公園
     - 国営公園（昭和記念公園、武蔵丘陵森林公園 など）
     - 自然観察園 / 都市緑地 / 自然教育園
     - 国定公園・国立公園内の散策コース
   - 候補ソース: 国土数値情報（都市公園 GeoJSON）、Wikipedia「<都県>の公園一覧」、OpenStreetMap `leisure=park` ノード、各市町村サイト。
   - 困難点を相談したいかもしれない: 規模カットオフ（小さすぎる児童公園は除く）、重複検出、命名統一。

2. **駐車場情報の取りこぼし削減**
   - 公式サイトには明らかに駐車場情報がある公園で「不明」になっているケース多い (現状 71 件)。
   - 失敗原因の分析が必要: heading が無いだけ／別 sub-page／PDF／JS レンダリング／用語ぶれ（「車でお越しの方」など）。
   - 一般者 vs 団体予約 を区別する分類器が要る — loose match を撤回した経緯と理由は本ファイル「Parking info」項参照。

3. **多言語対応** (HTML demo)
   - 現状は日本語のみ。優先: 英語 → 簡体中文 → 繁体中文。
   - 戦略候補:
     - UI 文言の i18n（フィルタラベル、ボタン、説明文）
     - 物種名: `species.common_name_en` は既に大半 ある。中国語名は新規取得が必要 (Wikipedia zh / GBIF vernacularNames)。
     - 公園名は基本日本語のまま、ふりがな or 英文表記を併記する程度で良いかも。
   - language toggle は静的 HTML 内で完結（i18n オブジェクトで切替）。
