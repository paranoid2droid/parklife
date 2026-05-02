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

Project is in maintenance + enrichment mode. Core pipeline shipped: 209 parks, **7,145 species, 99k observations**. Code + Pages site at <https://github.com/paranoid2droid/parklife>; demo published from `docs/` at <https://paranoid2droid.github.io/parklife/>. Active sessions 2026-05-01/02: shipped multilingual demo UI + Wikidata zh densification, taxonomy display cleanup, map fix, iNat photo backfill, Japanese-name backfill, eBird bird enrichment, bird-card eBird species links, language-aware iNat links, MVP species observation-guide modal, modal source labels, a multi-photo species modal carousel, demo data-source filter, unclassified display cleanup, detailed animal taxonomy cleanup, user-friendly top-level observation groups, and multilingual species-level profiles with source URLs. Current demo export has 7,052 visible species; 6,521 have at least one image, 858 visible species have 5-image galleries, 24 visible species have curated profiles in ja/en/zh/zhT with source URLs, and top-level groups are observation-friendly while detailed `taxon_group` is retained as `sp.tg`.

## In progress

*(none — nothing mid-flight at handoff time)*

## Blocked / waiting

- **User decisions still open**: default state of taxon-checkbox filter on demo (all-checked vs. localStorage memory) — see TODO #6 follow-up if revisiting filter UX.

## Next up

Mirror of the user's prioritized TODOs (recorded 2026-04-30). Pick from the top unless the user redirects.

1. **Expand park coverage beyond 都立/県立** — current 209 misses 国営/区立/市立/自然観察園. Discuss difficulties before scraping. Sources: 国土数値情報, Wikipedia 都県別公園一覧, OSM `leisure=park`.

2. **Reduce parking-unknown count (71 NULL)** — investigate per-page why classifier misses. Constraint: `団体予約のみ可` ≠ `公開駐車場あり`; must distinguish before loosening matching.

3. **Demo: multi-language toggle** — ✅ shipped 2026-05-01 in `d1d4ac0`. UI order: 日本語 / English / 简体中文 / 繁體中文. Language persists via `localStorage('parklife.lang')`; names/search/sort/group labels/parking labels localize in `scripts/export_html.py`.

   **Future task: language coverage/quality polish**:
   - Current DB coverage: `common_name_ja` 5,084/7,137 species; `common_name_en` 3,431/7,137; zh-Hans aliases cover 4,591 species; zh-Hant aliases cover 260 species.
   - Current demo export coverage after Japanese-name backfill: Japanese missing+English fallback 696/7,044 visible species (down from 1,797); English 3,414/7,044; 简体 4,534/7,044; 繁體 258/7,044.
   - `scripts/wikidata_zh.py` exists and has already run once (Wikidata SPARQL via `wdt:P225`); remaining gap is mostly Traditional Chinese coverage/label quality, not UI plumbing.
   - `scripts/backfill_ja_from_inat_cache.py` and `scripts/wikidata_ja.py` exist for Japanese-name repair. Avoid English Wikipedia-title backfill: tested briefly and it caused unsafe generic-name matches.
   - Recommended next step when revisiting language: add OpenCC-style Hans→Hant fallback for display/export so Traditional UI does not fall back to Japanese for most species. Optional second pass: targeted zh.wikipedia taxobox harvest for missing/high-traffic species.
   - Keep raw aliases first-class; do not overwrite Japanese names.

4. **External occurrence-data enrichment** (Gap #10 in SUMMARY.md), priority order:
   - **eBird** ✅ shipped 2026-05-02. Added `scripts/ebird.py`; run with `EBIRD_API_KEY=<token> .venv/bin/python -m scripts.ebird`. Uses recent nearby observations (`data/obs/geo/recent`) with 2km radius / 30-day lookback, caches under `data/cache/ebird/`, inserts `location_hint='eBird'`. Full run: 209 parks, 208 network calls + 1 cache hit, 0 errors, 4,884 eBird observations; bird species count now 380.
   - **GBIF** ✅ both passes shipped: occurrence (2026-04-30, 45k obs, +4k species) and vernacular (2026-05-01, +3431 en / +170 zh aliases). Chinese coverage is thin in GBIF — TODO #3 will need Wikipedia zh interlanguage links to densify.
   - **いきものログ** (env.go.jp) — Japan MoE, all taxa, gov-curated. No public API; bulk CSV ingest. Highest data quality, lowest convenience.
   - Skipped (evaluated): FishBase, MushroomObserver, Pl@ntNet.

5. **Demo: data-source filter** — ✅ shipped 2026-05-02. Top-bar selector ("全て / 公園公式 / iNaturalist / GBIF / eBird") filters map and selected-park species list by per-pair source codes exported from `observation.location_hint` / `source.url`. Current pair counts in demo export: official 2,041; iNat 27,022; GBIF 45,055; eBird 4,884.

6. **Demo: checkbox-filtered species list + sort controls** — ✅ shipped 2026-04-30. Sort options: 出現公園数 / 名称（日本語）/ 学名. Group checkboxes + sort persisted via localStorage (`parklife.hiddenGroups`, `parklife.speciesSort`).

   **Follow-up** (decided 2026-04-30, not yet done): better frequency metric. Currently sort uses `sp.n` = global count of parks containing the species. Two improvements queued:
   - Acquire **per-park observation count** (would require adding a `park_species.obs_count` column or surfacing existing `observation` counts to the export) — most accurate.
   - Until that exists, **constrain the `sp.n` fallback to geographically nearby parks** so a 関東-wide common species doesn't dominate over a locally-clustered one. Define "nearby" via lat/lon radius (e.g. 30 km) or by prefecture.
   - When multilingual support (TODO #3) lands, name sort should switch to the active UI language's name field, not always Japanese.

7. **Species observation-guide profiles** — MVP shipped 2026-05-02 in `scripts/export_html.py`: photo hover/tap shows a 🔍 button; clicking opens a modal with enlarged photo, difficulty score, season/source clues, and group-based finding tips in all UI languages.

   **Follow-up**:
   - ✅ First `species_profile` data layer shipped 2026-05-02: schema in `parklife/db.py`, seed script `scripts.seed_species_profiles`, export field `sp.pr`, and modal profile rendering. Current seed has 24 curated profiles in ja/en/zh/zhT and structured `source_urls`. Continue by adding more entries to `PROFILES_JA` + `PROFILES_EN_ZH`, then run `.venv/bin/python -m scripts.seed_species_profiles && .venv/bin/python -m scripts.export_html && cp data/export/index.html docs/index.html`.
   - ✅ Source names shipped 2026-05-02: modal now shows 公園公式 / iNaturalist / GBIF / eBird from per-pair observation provenance.
   - Improve difficulty using per-park `observation_count`, month selected, and source diversity; current MVP uses global park count + pair source count + taxon-group heuristics.
   - ✅ Multi-photo modal carousel shipped 2026-05-02: added `species_photo` table, `scripts.collect_species_photos`, exported `sp.imgs`, and modal left/right buttons + keyboard arrows + touch swipe. Current DB/docs cover 510 high-frequency species with 5 images each; continue with `.venv/bin/python -m scripts.collect_species_photos 500 5` to add the next 500 species.
   - 2026-05-02 partial follow-up: user paused a long `collect_species_photos 1000 5` run. It had already added more rows before stopping; current visible export has 858 species with 5-image galleries. Resume later with `.venv/bin/python -m scripts.collect_species_photos 1000 5` during a long wait.
   - Browser automation was unavailable locally (`playwright` not installed); only JS syntax/static structure were checked before deploy.

## Recent sessions

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
