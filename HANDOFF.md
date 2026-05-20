# HANDOFF — cross-agent live state

Shared between Claude Code and Codex (and any other agent the user adds). This file is the **source of truth for what to do next**. SUMMARY.md is deep history; RUN_LOG.md is per-batch operational log; this file is the live baton.

## Protocol

**On session start** (before doing anything else):
1. Read this whole file.
2. Read CLAUDE.md if you haven't this session (project knowledge, won't change often).
3. Skim the last 2–3 entries under "Recent sessions" to know what just happened.

**On session end** (or before quota runs out):
1. Update **Status**, **In progress**, **Blocked**, **Next up** to reflect reality *now*.
2. Prepend one new entry to **Recent sessions** — date, agent name, 1–3 bullets on what changed. Keep entries ≤6 lines.
3. If you started something and didn't finish, leave concrete pointers in **In progress** (file paths, line numbers, the exact next command). Assume the next agent has zero memory of this session.
4. Trim **Recent sessions** to the last ~15 entries; older history belongs in SUMMARY.md or git log.

**Editing rules**:
- Never delete another agent's "In progress" notes without confirming the work is done. If unsure, move them to "Blocked / waiting" with a question.
- Concrete > vague. "Run `.venv/bin/python -m scripts.X`" beats "continue the import".
- Mark agent in entries: `(Claude)` or `(Codex)`.

---

## Status

Project is in maintenance + enrichment mode. Core pipeline shipped: **461 parks, 9,728 species, 191k observations** (after 2026-05-18 dedup of 21 P13-introduced duplicates against existing seeded parks; see `scripts/merge_duplicate_parks.py`). Code + Pages site at <https://github.com/paranoid2droid/parklife>; demo published from `docs/` at <https://paranoid2droid.github.io/parklife/>. Active sessions 2026-05-01/03 shipped multilingual demo UI, map fix, iNat/GBIF/eBird enrichment, Japanese-name backfill, language-aware external links, data-source filter, user-friendly taxonomy groups, species modal with profiles/source links/difficulty/multi-photo carousel, mobile UX improvements, category-first species panel, location-based recommendation, expanded bird/insect profile batches, and broad iNat photo fallback. Current committed demo export has 7,052 visible species; 6,521 have at least one primary image; local DB now has 32,402 `species_photo` rows, 6,593 species with gallery rows, and 6,369 species with 5+ gallery photos; 1500 species have curated profiles in ja/en/zh/zhT (6000 rows) — continuous batch sweep through commit `896a0ff` (batch 153, **1500-species milestone reached**). Top-level groups are observation-friendly while detailed `taxon_group` is retained as `sp.tg`.

## In progress

*(none — long-running photo gallery sweep completed and final docs were exported)*

## Blocked / waiting

*(none currently)*

## Next up

Active TODOs only. Shipped items are pruned to git log + Recent sessions. Pick from the top unless the user redirects.

### Active

1. **Official-URL backfill for P13 parks — second pass** *(opened 2026-05-18; first pass shipped 2026-05-20 — 105/253 filled; 148 remain)*
   - First pass (shipped `4eeaad5`): `scripts/wikipedia_park_url.py` extracts URLs from JA Wikipedia infoboxes / `{{Official}}` templates / `== 外部リンク ==` links. Result by pref: kanagawa 43/72 (60%), tokyo 25/60 (42%), saitama 23/70 (33%), chiba 14/51 (27%). The 133 parks with no Wikipedia article are long-tail 区立/市立/town parks; the 15 with an article but no extractable URL are weird-infobox edge cases. Tried OSM Overpass `website=*` first (`scripts/osm_park_url.py`); `website` tag effectively unused on JP parks (0/5), kept for reference.
   - **Second pass — 148 P13 parks still lacking URL** (current breakdown: chiba 37, kanagawa 29, saitama 47, tokyo 35):
     - **A.** Scrape prefecture park-association indexes by name: tokyo-park.or.jp + tmpa.or.jp (Tokyo); kanagawa-park.or.jp (Kanagawa); cga-net.jp (Chiba); parks.or.jp (Saitama). Reuse `parklife.fetch.fetch_cached_or_new`; cache under `data/cache/park_url_search/`. Expected to mostly hit the prefecture-managed entries.
     - **B.** For 区立/市立 parks (largest residual): scrape the municipality's 公園緑地課 / 公園課 index. The `municipality` column is already populated for most P13 rows, so build per-municipality scraper lookup tables.
     - **C.** Manual curation: 148 is small enough that an afternoon of name-by-name search would close most of it; write the chosen URLs to `data/manual_park_urls.json` and load via a one-shot script like `scripts/apply_manual_species` does for species.
     - Quick check: `sqlite3 data/parklife.db "SELECT prefecture, COUNT(*) FROM park WHERE slug LIKE 'p13-%' AND (official_url IS NULL OR official_url='') GROUP BY prefecture;"`.
     - Sample 5 names to inspect what's left: `sqlite3 data/parklife.db "SELECT prefecture, name_ja, municipality FROM park WHERE slug LIKE 'p13-%' AND (official_url IS NULL OR official_url='') ORDER BY RANDOM() LIMIT 5;"`.

2. **Continue species_profile curation** *(paused at 1500 / 2026-05-18 — resumable)*
   - **Current state**: 1500 species × 4 langs (6000 rows) curated. Last commit `894cf16`. Sweep started at 49 species (2026-05-14) and ran through batches 1–153.
   - Sidecar workflow: append entries to `data/species_profiles_extra.json`, then run `.venv/bin/python -m scripts.seed_species_profiles && .venv/bin/python -m scripts.export_html && cp data/export/index.html docs/index.html && git commit && git push`. Hant is auto-generated from Hans via OpenCC-like table; each profile carries ja/en/zh/zhT + `source_urls` (Wikipedia + iNaturalist + eBird when applicable).
   - Selection: top-N most-widespread visible species not yet profiled. Quick query: `sqlite3 data/parklife.db "SELECT s.scientific_name, s.common_name_ja, COUNT(DISTINCT ps.park_id) AS np FROM species s JOIN park_species ps ON ps.species_id=s.id LEFT JOIN species_profile sp ON sp.species_id=s.id WHERE sp.species_id IS NULL AND s.scientific_name IS NOT NULL GROUP BY s.id ORDER BY np DESC LIMIT 12;"`.
   - The 1500 mark covers everything observed in ≥21 parks. Remaining unprofiled species mostly appear in ≤20 parks (long-tail). Resume on user request.

3. **いきものログ ingest (env.go.jp)** *(not started)*
   - Japan MoE platform, all taxa, gov-curated. No public API; bulk CSV ingest. Highest data quality, lowest convenience — would be the most authoritative source we don't yet use.
   - eBird + GBIF + iNat already cover most of what's reachable; いきものログ would mainly add rarer/locally-restricted records and validate edge cases.
   - FishBase / MushroomObserver / Pl@ntNet evaluated and skipped as lower ROI for this scope.

### Follow-ups (defer until needed)

- **Chinese name coverage** *(post-`f3078aa`, 4,948 / 7,145 visible species have zh)*
  - Manual curation for high-frequency species still missing zh — `query top --group X` and seed `species_profile` zh fields directly. Most impact per hour of work.
  - Try newer sp2000 release when published (current is `chinacol2023`).
  - iNaturalist `?locale=zh-CN` taxon names for high-traffic taxa not in CoL China.
  - Keep raw aliases first-class in `species_alias` (lang=`zh-Hans`/`zh-Hant`); never overwrite Japanese names. Avoid English-Wikipedia-title backfill (tested 2026-05-02, unsafe).

- **Park coverage beyond P13** *(post-`e1f93b2`, 461 parks)*
  - P13 is 2011 snapshot — when MLIT ships a 2024+ refresh, re-run `scripts/p13_seed.py` (idempotent on slug hash). **Bump the dedup radius to ≥1 km** to avoid repeating the 2026-05-18 duplicate-park bug (500 m missed 590 m-offset entries).
  - Consider relaxing filters: 街区/近隣公園 ≥ 5 ha exist and were filtered out; 自然観察園 inside larger parks remain invisible.
  - Beyond P13: 国営公園 (~17 nationwide), 区立 nature observation gardens, 都市林 < 5 ha that are genuinely forested — would need manual curation or OSM `leisure=park`/`landuse=forest` cross-reference.

- **Photo gallery** *(post-`87f5553`, 78% visible-species coverage)*
  - ~2,150 visible species still have no photo. Periodically re-run `scripts.collect_species_photos` (broad fallback) as iNat acquires more.
  - Truncate verbose Commons `extmetadata.Artist` HTML to first author when "Multiple contributors" lists appear.
  - Add Flickr / GBIF media as a 3rd hero source for taxa with neither iNat nor Commons coverage.

- **Species sort: regional `sp.n` tiebreaker** *(post-`a85c1ba`)*
  - Current `freq` sort: `pair.oc` desc primary, `sp.n` desc tiebreaker. When two species both have 1 record at the selected park, global spread tiebreaker favors 関東-wide commons over locally-clustered species. Precomputed `sp.regional_n` per (species, prefecture) would fix this; defer until a user complaint surfaces.

## Recent sessions

### 2026-05-16/onward (Claude) — TODO #6 species_profile mass expansion
- Added `data/species_profiles_extra.json` sidecar + loader in `scripts/seed_species_profiles.py` so future curation grows without ballooning the Python source.
- Wrote ~355 new 4-language profiles across many batches (commits `45071e1`, `2566f64`, `2fb984d`, `c501c22`, `a402abb`, `17d0125`, `c20f2f3`, `4e59dc6`, `7469e61`, `714d647`, `19f7e65`, `cd803ef`, `1b9cb3f`, `ec81bcd`, `6a999a7`, `2768097`, `16cc2df`, `23989b5`, `6697a88`, `a0273c5`, `3936f00`, `b00121d`, `77bd061`, `8ad9627`, `fc71a22`, `2c38f47`, `b78c798`, `fd5d5e6`, `e4162df`). Profile total: 49 → ~405 species.
- Coverage strategy: high-frequency visible species first (sort by global park count). Targeted ranks 1–~430. Many include safety notes (hornets, toxic plants, invasive species) and cultural context (春の七草, festivals, traditional uses).
- HANDOFF #6 updated with sidecar workflow and a SQL one-liner to find the next batch of candidates.

### 2026-05-16 (Claude) — TODO #3 parking-unknown closed
- Added `scripts/osm_parking.py` using OSM Overpass `amenity=parking` within 300 m. Replaces and outscales the per-page scrape approach: it handles both the 45 curated NULLs *and* the 273 P13 parks (no `official_url`) in one pass.
- Re-ran `scripts/geocode.py` first to fill 14 missing coordinates that had been blocking the OSM query. Manual UPDATE for the 3 final parks whose parenthesised Japanese names defeat Nominatim. NULL count 318 → 0. Commit `6a9ca7d`.

### 2026-05-16 (Claude) — TODO #7 photo quality + attribution
- Added `scripts/repopulate_species_photos.py` — pure-local rebuild from cached iNat data with diversity dedup `(user, day)` / `(user, week, ~1km)`, CC-license filter, 5→6 target. 34,979 iNat rows for 6,229 species.
- Added `scripts/wikicommons_hero.py` — Wikidata P18 + Commons imageinfo; 5,822 hero rows inserted (58.7% of visible species), 73 rejected by license filter. Caches under `data/cache/wikidata_p18/` and `data/cache/commons/`.
- Schema: `species_photo.source_url` column (ALTER TABLE on live DB, `parklife/db.py` updated). Export shape `sp.imgs = [[url, attribution, source_url], ...]`; modal shows credit caption with photographer · license · source ↗ link.
- Demo HTML 8.2 → 12.9 MB. Commit `87f5553`.

### 2026-05-16 (Claude) — TODO #5 freq-sort improvement
- Changed `sortGroupItems` in `scripts/export_html.py` so the freq sort ranks by `pair.oc` (per-park observation count) descending, with `sp.n` (global) as tiebreaker. Updated labels in ja/en/zh/zhT to reflect the new meaning. Commit `a85c1ba`.
- Geographic-radius fallback for tiebreakers deferred to follow-up; the per-park record count already addresses the main pain point of 関東-wide commons dominating every park's list after the 209→482 expansion.

### 2026-05-15/16 (Claude) — TODO #2 P13 expansion shipped
- Added `scripts/p13_seed.py`: downloads 国土数値情報 P13 GML zips for 4 prefectures, filters to biodiv park types ≥ 5 ha, dedupes by 500 m radius vs existing parks, writes `data/seeds/<pref>-p13.json`. +273 parks (209 → 482). Cache: `data/raw/p13/`.
- Ran full geographic enrichment: iNat +21,792, GBIF +66,406, eBird +4,042 obs (using the EBIRD_API_KEY the user provided in-session). Re-ran zh backfill pipeline on the new 2,770 species: +2,027 zh-Hans + +65 zh-Hant aliases total.
- DB now 482 parks / 9,915 species / 191k observations / 131k park_species pairs. Commit `e1f93b2`.

### 2026-05-15 (Claude) — Chinese name coverage follow-up
- Cleaned 48 pinyin "zh" aliases (e.g. "Bai Guo" / "Felis catus") via `scripts/cleanup_zh_aliases.py`; re-processed GBIF cache to recover 6 Han-only names previously masked by `pick_best`.
- Imported Catalogue of Life China 2023 DwC-A (288k taxa) via `scripts/sp2000_import.py`: +231 zh-Hans aliases by exact / binomial-prefix match. Raw archive lives under `data/raw/sp2000/` (gitignored).
- Final visible zh coverage 4,720 → 4,948 (+228 net of cleanup); any-zh 64.6% → 69.3%. Commit `f3078aa`.

### 2026-05-14 (Claude) — Chinese name coverage pass
- Fixed display fallback in `scripts/export_html.py`: zh/zhT users now see English (with `.name-fallback` dotted-underline + "暂无中文名" tooltip) instead of silently falling back to Japanese. Modal/card/alt sites now go through `displayNameHtml()` / `escapeHtml()`. Commit `15cbd4c`.
- Added `scripts/wikidata_zh_broad.py` (P1843 + altLabel SPARQL) and `scripts/wikipedia_zh_direct.py` (zh.wiki redirect resolution). Combined gain: +87 new aliases inserted; visible zh coverage 4,619 → 4,720. Commit `909bf31`.
- TODO #1 marked partial; follow-up subtasks queued (sp2000 harvest, GBIF zh re-confirm, manual curation).

### 2026-05-05 (Codex) — PR #2 conflict assist + merge confirmation
- Resolved PR #2 conflict block for `scripts/export_html.py` (kept OpenCC conversion with conservative fallback when `opencc` is unavailable).
- Verified GitHub state after user merge confirmation: PR queue is clean (0 open), and `main` includes both zhT fallback commits (`4e2af26`, `e24f3de`).
- Updated handoff queue: Traditional Chinese fallback item is now marked shipped; next practical item remains small `species_profile` expansion.

### 2026-05-03 (Codex) — local session wrap-up
- Prepared handoff for continuing from web: working tree was clean after push; latest deployed commit is `2cbe3be Complete iNat photo broad fallback`.
- No known in-progress batch remains; the broad iNat photo fallback completed before this handoff. If continuing photo work later, start from the recorded 230 `<5 photos` iNat candidates / 552 visible no-gallery species rather than rerunning the whole sweep.

### 2026-05-03 (Codex) — broad iNat photo fallback
- Added a broad fallback path to `scripts.collect_species_photos`: if research-grade/non-captive iNat photo results are below target, query cached broader iNat observation photos under `data/cache/inat_photos_broad/`.
- Ran the fallback over 477 remaining `<5 photos` iNat candidates: 389 species gained photos, +1,054 `species_photo` rows, no new `HTTP 429`.
- Regenerated `docs/index.html`; final local counts: 32,402 photo rows, 6,593 species with gallery rows, 6,369 with 5+ photos, 230 iNat candidates still below 5.

### 2026-05-03 (Codex) — modal timing fix + photo sweep deployed
- Replaced modal record-month display with natural-history observation timing hints; park clues now show record count/source only, avoiding misleading "only seen in Apr/Dec" wording for year-round species.
- Long `collect_species_photos 0 5` run completed: 5,398 tried, 4,997 with photos, +24,234 photo rows. Exported final docs; DB now has 30,646 species_photo rows and 6,013 species with 5+ photos.
- Same-day cooldown retry of the remaining 610 candidates saw no new 429s and added 702 more photo rows; DB now has 31,348 species_photo rows and 6,146 species with 5+ photos.

### 2026-05-03 (Codex) — location-based recommendation
- Added browser-geolocation recommendation to `scripts/export_html.py`: nearest data park is selected only when the user is in Japan and within 80km of available park data.
- Default fallback changed from most-diverse park to nearest park around Tokyo Station, matching the "Tokyo center" fallback.
- Regenerated `docs/index.html`; Python compile and generated JS `node --check` passed.

### 2026-05-03 (Codex) — profile batch + photo backfill running
- Started long-running photo gallery sweep: `.venv/bin/python -m scripts.collect_species_photos 0 5` in exec session `27094`; keep it running and export docs after it finishes.
- Added per-species exception handling to `scripts.collect_species_photos` so one failed taxon does not stop the batch.
- Added 20 high-frequency bird profiles to `scripts.seed_species_profiles`; current DB/docs have 44 profiled species / 176 localized rows.

### 2026-05-03 (Codex) — category action placement
- Moved Select all / Select none quick actions from their own controls row into the species-count line to save vertical space.
- Regenerated `docs/index.html`; Python compile and generated JS `node --check` passed.

### 2026-05-02 (Codex) — category-first species panel
- Changed per-park category checkboxes from hide-by-default to select-by-default-empty (`parklife.selectedGroups.v2`), so species cards do not render until a category is chosen.
- Added localized Select all / Select none quick buttons; single selected category expands, multiple selected categories collapse by default.
- Regenerated `docs/index.html`; Python compile and generated JS `node --check` passed.

### 2026-05-02 (Codex) — simplify mobile view switching
- Removed the bottom-right mobile view toggle and pure-map mode from `scripts/export_html.py`.
- Mobile now has two states only: default split map+detail, and marker-focused detail list; the in-panel map button returns to split view.
- Regenerated `docs/index.html`; Python compile and generated JS `node --check` passed.

### 2026-05-02 (Codex) — mobile detail flow + partial photo commit
- Paused the in-progress `scripts.collect_species_photos 1000 5` run at user request and exported the partial result: current docs have 1,282 visible species with 5-image galleries.
- Improved mobile UX in `scripts/export_html.py`: marker taps focus the species list, and selected-park headers now include a localized map-return button.
- Upgraded modal difficulty scoring to use per-park observation counts and source diversity; `node --check` passed on the generated client JS.

### 2026-05-02 (Codex) — multilingual profiles + source URLs
- Extended `species_profile` with `source_urls` and updated `scripts.seed_species_profiles` to write 4 language rows (ja/en/zh/zhT) for each curated species.
- Seed now generates structured source URL records for Wikipedia, iNaturalist, and eBird where applicable; modal renders clickable profile reference links.
- Current DB/docs export: 24 species profiles in each language (96 rows), all with source URLs; JS syntax check passed.

### 2026-05-02 (Codex) — species-level profile MVP
- Added `species_profile` schema (`species_id`, `lang`, `summary`, `habitat_hint`, `finding_tips`, `sources`, `updated_at`) and `scripts.seed_species_profiles`.
- Seeded 24 curated Japanese profiles for common/high-impact species (birds, insects, reptile/amphibian, crustaceans, plants, fungus, fish, mammal), including アメリカザリガニ, サワガニ, ハスノハカシパン.
- Export now includes `sp.pr`; modal shows profile sections when available and falls back to group-level guide text otherwise. Regenerated `docs/index.html`; JS syntax check passed.

### 2026-05-02 (Codex) — user-friendly observation groups
- Reworked demo top-level grouping in `scripts/export_html.py`: DB `taxon_group` stays detailed, export now maps to observation groups (`plant`, `bird`, `insect`, `arachnid_myriapod`, `crustacean`, `fish`, `herp`, `mammal`, `mollusk`, `small_aquatic`, `mushroom`).
- Exported detailed DB group as `sp.tg` and added modal "詳しい分類 / Detailed group" display, so examples like ハスノハカシパン show top-level `small_aquatic` but detailed `echinoderm`.
- Regenerated `docs/index.html`; current group counts: plant 2955, insect 2321, mollusk 402, bird 380, mushroom 356, fish 262, spider/myriapod 145, crustacean 87, mammal 51, herp 50, other aquatic/small animals 43.

### 2026-05-02 (Codex) — detailed animal taxonomy cleanup
- Audited all visible `その他動物`: 242 species / 786 park pairs were `animalia` with `taxon_group=NULL`, mostly GBIF records for crustaceans, fish with missing class, echinoderms, myriapods, cnidarians, annelids, and flatworms.
- Expanded GBIF taxonomy mapping, added `scripts.repair_animal_groups`, and backfilled all 242 species. User examples now classify as: アメリカザリガニ/サワガニ → `crustacean`, ウグイ → `fish`, ハスノハカシパン → `echinoderm`.
- Added localized demo labels/guide text for the new groups and hid empty global filter options; current exported `other_animal` species count is 0.

### 2026-05-02 (Codex) — unclassified display cleanup
- Audited visible `❓ 未分類` species: all 23 were plant/cultivar/common plant names with missing `kingdom/taxon_group`.
- Added those plant names to `scripts.fix_audited_species`, ran it, then re-ran `scripts.dedupe` and `scripts.export_html`; current export has 0 `unclassified` species and no `未分類` text.
- Kept the fallback group internally, but its user-facing label is now `🐾 その他生き物` / `Other life` / `其他生物`.

### 2026-05-02 (Codex) — data-source filter
- Added top-bar source selector (`全て / 公園公式 / iNaturalist / GBIF / eBird`) in `scripts/export_html.py`; it filters both map markers and the selected-park species panel.
- Filter uses per-pair source codes already exported in `DATA.pairs`; source changes now re-render the selected park list immediately.
- User paused a long photo-gallery backfill run; partial result is kept in local DB/docs, bringing visible 5-image gallery coverage to 858 species.

### 2026-05-02 (Codex) — multi-photo species modal
- Added `species_photo` schema and `scripts/collect_species_photos.py`, which caches iNat observation photo queries under `data/cache/inat_photos/` and stores 3–5 gallery URLs per species.
- Ran the script for 510 high-frequency species total, adding 2,550 local DB photo rows; export now includes `sp.imgs` and 510 species have 5-image galleries.
- Modal now supports previous/next buttons, keyboard arrows, and touch swipe; gallery export embeds iNat `medium` URLs for fast opening, then lazily upgrades the visible image to `large` and preloads adjacent images. Image area is fixed-height/responsive (`clamp`) with `<img object-fit: contain>` for stable layout without cropping. Regenerated `docs/index.html` (3.8 MB) and `node --check` passed.

### 2026-05-02 (Codex) — modal source labels + photo-carousel planning
- Export now derives per park-species source codes from `observation.location_hint` / `source.url` and appends them to `DATA.pairs`; modal displays localized source names instead of only a count.
- Simplified the 🔍 icon styling: removed circular background/border, kept a plain icon with text shadow.
- Checked multi-photo feasibility: current caches expose representative `default_photo`, not stable per-species galleries. Next step should add a cached `species_photos`/`sp.imgs` layer from iNat observation photos.

### 2026-05-02 (Codex) — observation-guide modal MVP
- Added photo hover/tap 🔍 buttons and a species modal in `scripts/export_html.py`; modal shows enlarged photo, difficulty score, season/source-count clues, and localized group-level finding tips.
- Difficulty is data-driven but heuristic: global park count (`sp.n`), selected-park source count (`pair.sc`), and taxon group adjustments.
- Regenerated `docs/index.html`; Node syntax check passed. Playwright was unavailable locally, so no browser-click automation was run.

### 2026-05-02 (Codex) — language-aware iNat links
- Updated species-card iNaturalist links to include `?locale=ja/en/zh` based on the active demo language; Simplified and Traditional Chinese both use iNat's `zh` locale.
- Regenerated `docs/index.html` and syntax-checked the generated client JS with Node.

### 2026-05-02 (Codex) — bird-card eBird links
- Added export of stored eBird species codes (`species_alias.lang='ebird'`) into `docs/index.html` as `sp.eb`; 185 exported, all bird-group species.
- Species cards now show an `eBird` external link when `sp.eb` is present, with language-aware `siteLanguage` for Japanese / Simplified Chinese / Traditional Chinese.
- Regenerated `docs/index.html` and syntax-checked the generated client JS with Node.

### 2026-05-02 (Codex) — eBird bird enrichment
- Added `scripts/ebird.py` using eBird recent nearby observations, 2km radius, 30-day lookback, cached under `data/cache/ebird/`; API key is env-only and not committed.
- Full run inserted 4,884 eBird observations across 209 parks (0 errors); dedupe/export regenerated docs. Stats now 7,145 species, 99,011 observations, 58,172 park-species pairs, 380 bird species.
- Verified no API token string in tracked files; `node --check` passed for generated `docs/index.html`.

### 2026-05-02 (Codex) — Japanese-name display repair
- Confirmed Japanese UI was falling back to English because 1,797 visible species had no `ja` display name but did have `en`.
- Added offline iNat-cache backfill (`scripts/backfill_ja_from_inat_cache.py`, +89 names) and Wikidata-by-scientific-name backfill (`scripts/wikidata_ja.py`, +1,362 names); regenerated `docs/`.
- Current visible demo fallback count: 696 species still have no Japanese name but do have English; English-Wikipedia-title backfill was tested and rejected as unsafe due generic-name false matches.

### 2026-05-01 (Codex) — iNat photo backfill for demo
- Extended `scripts.ensure_inat_taxon` with `--missing-photo`, park-count ordering, microbe exclusion, cache accounting, and 1 req/sec network throttling.
- Ran full missing-photo pass against iNaturalist: visible-demo photo coverage improved from 3,005/7,044 to 6,521/7,044 species; 523 remain missing.
- Regenerated `docs/index.html` (2.3 MB) and syntax-checked embedded scripts. Local `data/parklife.db` now has the new `photo_url` values; DB/cache remain gitignored.

### 2026-05-01 (Codex) — demo taxonomy display cleanup
- Fixed `scripts/export_html.py` demo-facing group mapping: fungi labeled as 菌類/Fungi/etc., unknown animalia shown as その他動物, microbe kingdoms hidden from demo.
- Collapsed plant subgroups (`plant/tree/shrub/herb/vine`) into one demo bucket: 植物 / Plants / 植物, avoiding confusing overlap in the per-park checkbox list.
- Regenerated `docs/index.html`; syntax checked embedded scripts with Node. Ready to commit/deploy before photo backfill.

### 2026-05-01 (Codex) — demo map fix
- Read project handoff/docs and reproduced blank demo map locally at `http://localhost:8000/`.
- Fixed `scripts/export_html.py`: renamed helper `L()` to `labels()` so it no longer shadows Leaflet's global `L`.
- Regenerated `docs/index.html`; browser verification shows map tiles/markers rendering again.

### 2026-05-01 (Claude) — Wikipedia zh langlinks pass shipped
- `scripts/wikipedia_zh.py`: batched 50 titles/req against ja.wiki then en.wiki fallback. Hit rate 31/3469 ja + 136/6902 en = ~2% — most species articles have no direct zh interlanguage link.
- 165 new zh aliases (164 Hans + 1 Hant). zh totals: 334 Hans + 3 Hant = 337.
- Still too thin for full multi-language UI; TODO #3 updated to flag Wikidata or zh.wiki taxobox harvest as next-step options.

### 2026-05-01 (Claude) — GBIF vernacular pass shipped
- Ran `scripts.gbif_vernacular` over 7103 species (~3 hr). 36 unmatched, 3431 English names filled, 682 ja names filled, 170 zh aliases (168 Hans + 2 Hant).
- Chinese coverage in GBIF is sparse (~2.4%) — TODO #3 multi-language will still need Wikipedia zh interlanguage links.
- Re-ran dedupe (no change to park_species count) + regenerated all exports. Pushed.

### 2026-04-30 (Claude) — TODO #4 GBIF main pass shipped
- Added `scripts/gbif.py` (per-park GBIF occurrence search, 1.5km radius, idempotent on `location_hint='GBIF'`) and `scripts/gbif_vernacular.py` (vernacular-name scaffold, not yet run).
- Ingested 45,203 GBIF observations across 207/209 parks. Species 2982 → 7137; park_species 28k → 57k.
- New TODO #5 added (data-source filter on demo) — user noticed only ~2% of obs are from original website scrape, rest is geographic enrichment.
- Permission allowlist extended for api.gbif.org + common pipeline scripts; pending cleanups: dedupe near-duplicate species (`Quercus crispula` vs `Q. mongolica subsp. crispula` etc.), and decide whether to hide microbial kingdoms (archaea/bacteria/chromista/protozoa) from the demo.

### 2026-04-30 (Claude) — TODO #6 shipped (was #5 before renumber)
- Implemented per-park species panel: group checkboxes + 3-way sort (出現公園数 / 名称 / 学名), all persistent via localStorage.
- Edits in `scripts/export_html.py` (CSS in HTML_TEMPLATE, JS in CLIENT_JS / `selectPark`). Regenerated `docs/index.html`.
- Added Follow-up note under TODO #5 for better frequency metric (per-park obs count, or geographically-constrained sp.n fallback).

### 2026-04-30 (Claude) — repo consolidation
- `git init` + first commit (9f3add9, 318 files), pushed to new <https://github.com/paranoid2droid/parklife>.
- Rewrote `scripts/deploy.py`: outputs to `./docs/` instead of `/tmp/parklife-demo/`; no longer auto-commits/pushes — review with `git status docs` and push manually.
- `.gitignore` extended: `data/parklife.db`, `data/cache/`, `data/export/`, `data/run_queue.*` all local-only.
- GitHub Pages configured: source = main / `/docs`. Live at <https://paranoid2droid.github.io/parklife/>.
- Old `parklife-demo` GitHub repo frozen (kept as-is, not updated). Local `/tmp/parklife-demo/` can be deleted.

### 2026-04-30 (Claude) — planning
- Added TODO #4 (eBird + GBIF + いきものログ enrichment, prioritized) and TODO #5 (checkbox-filter + sort UI on demo).
- Set up HANDOFF.md + AGENTS.md as the cross-agent sync mechanism (per user request to start collaborating with Codex).
