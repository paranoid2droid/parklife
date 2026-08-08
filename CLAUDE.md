# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A scraped database of flora and fauna observed in Japanese parks, built from each park's official website. Initial scope: parks managed by Tokyo (都立), Kanagawa (県立), Chiba (県立), and Saitama (県立). Output is a single SQLite file at `data/parklife.db`.

## Commands

All Python work runs in the project venv (`Python 3.13`):

```bash
.venv/bin/pip install -r requirements.txt  # install deps

# pipeline (run in order on a fresh DB)
.venv/bin/python -m scripts.init_db                  # 1. (re)create schema
.venv/bin/python -m scripts.fetch_seed_lists         # 2. prefecture index pages
.venv/bin/python -m scripts.build_seeds              # 3. parse → data/seeds/*.json
.venv/bin/python -m scripts.load_seeds               # 4. JSON → park table
.venv/bin/python -m scripts.scrape_tokyo             # 5. all 137 Tokyo parks
.venv/bin/python -m scripts.scrape_nanasawa          # 6. one-off (Kanagawa nanasawa)
.venv/bin/python -m scripts.scan_tokyo_animals       # 7. find animal narratives
.venv/bin/python -m scripts.extract_tokyo_animals    # 8. ingest from main pages
.venv/bin/python -m scripts.list_animal_sub_anchors2 # 9. find sub-page targets
.venv/bin/python -m scripts.scrape_subpages          # 10. fetch+ingest sub-pages
.venv/bin/python -m scripts.geocode                  # 11. lat/lon via Nominatim
.venv/bin/python -m scripts.inaturalist              # 12. iNat enrichment (long)
.venv/bin/python -m scripts.extract_kanagawa_pages   # 13. non-Tokyo HTML scan

# enrichment passes (run when desired; all idempotent, all cached)
.venv/bin/python -m scripts.inaturalist_captive      # cultivated plants (captive=true)
.venv/bin/python -m scripts.ensure_inat_taxon        # iNat taxon_id for species
.venv/bin/python -m scripts.collect_photo_urls       # photo URLs from cached iNat data
.venv/bin/python -m scripts.plant_phenology          # narrow flowering months via iNat
.venv/bin/python -m scripts.gbif_admin --group insect # recover GBIF coord-less specimens as the 'admin:municipality' tier (RE-RUN scripts.dedupe after); --dry-run

# parking classification (run in this order after ingesting new parks; idempotent, cached)
.venv/bin/python -m scripts.extract_parking          # 1. text verdict from cached HTML (authoritative)
.venv/bin/python -m scripts.reclassify_parking       # 2. OSM-tagged rows → retry text on alt cached pages
.venv/bin/python -m scripts.osm_parking              # 3. remaining NULLs → OSM presence (absence stays NULL)

# normalization + dedup (run after each ingestion phase, in order)
.venv/bin/python -m scripts.normalize                # Wikipedia ja → species
.venv/bin/python -m scripts.apply_manual_species     # data/manual_species.json fallback
.venv/bin/python -m scripts.repair_kingdoms          # taxon_group → kingdom backfill
.venv/bin/python -m scripts.backfill_observations    # link observation.species_id
.venv/bin/python -m scripts.dedupe                   # rebuild park_species (deduped per pair)
.venv/bin/python -m scripts.backfill_display_gaps    # card polish: common_name_ja from kana alias (collision-guarded) + photo_url from park-local photo; --dry-run
.venv/bin/python -m scripts.fetch_inat_ja_names      # fill common_name_ja from iNat locale=ja for tid-bearing Latin-only species (Japanese-only, collision-guarded, cached); --dry-run
.venv/bin/python -m scripts.merge_dupname_synonyms   # merge same-ja-name genus-reassignment/gender-variant synonyms (one has tid); RE-RUN scripts.dedupe after; --dry-run

# autonomous queue (no Claude required)
.venv/bin/python -m scripts.run_pending              # process data/run_queue.txt under fcntl lock
# To enable launchd auto-resume across reboots / sessions:
#   cp com.parklife.queue.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.parklife.queue.plist

# exports
.venv/bin/python -m scripts.export_json              # data/export/parklife.json
.venv/bin/python -m scripts.export_park_md           # data/export/parks_md/<pref>/<slug>.md
.venv/bin/python -m scripts.biodiversity_report      # data/export/REPORT.md
.venv/bin/python -m scripts.bird_seasonal_report     # data/export/BIRDS.md
.venv/bin/python -m scripts.endemic_report           # data/export/ENDEMIC.md

# static demo site (productization P2 — the recommended deploy: free static host, no server)
.venv/bin/python -m scripts.export_static            # DB → site/ (sharded static JSON, ~5k files)
cd site && python -m http.server 8091                # local preview (real Chrome test: webapp/e2e_test.py, BASE=http://127.0.0.1:8091/)
scripts/deploy_pages.sh                              # build + force-push site/ to orphan gh-pages (keeps main's git slim)

# query CLI
.venv/bin/python -m scripts.query stats              # overall counts
.venv/bin/python -m scripts.query bloom 4            # species in season for month N
.venv/bin/python -m scripts.query where ソメイヨシノ # parks with this species
.venv/bin/python -m scripts.query park jindai        # one park's full list
.venv/bin/python -m scripts.query species --group bird --limit 50
.venv/bin/python -m scripts.query prefecture tokyo
.venv/bin/python -m scripts.query top --group bird   # most-widespread species
.venv/bin/python -m scripts.query near 35.6586,139.7454 --radius_km 5
.venv/bin/python -m scripts.query diverse --limit 25 # parks ranked by diversity
```

The venv was created with `/opt/homebrew/bin/python3.13 -m venv .venv`. Deps are pinned in `requirements.txt`.

`scrapling` is installed but its browser backend (`scrapling install`, ~200 MB Chromium) is **not**. Add it only when a target site needs JS rendering — the four pref sites we care about all serve static HTML, accessed via `curl_cffi.requests` with `impersonate="chrome"` (Python's default TLS gets rejected by `pref.kanagawa.jp` etc).

## Architecture

The pipeline has four stages, each backed by a table in `data/parklife.db`:

1. **Seed** (`data/seeds/<prefecture>.json` → `park` table) — curated list of parks with official URLs. JSON is intentional: avoids a YAML dependency, easy to diff. Loaded via `parklife.seeds.load`.
2. **Fetch** (`source` table + `data/raw/`) — every fetched URL is recorded with timestamp, sha256, and a path to the cached HTML. Re-scrapes are idempotent on `(url, fetched_at)`. Helper: `parklife.fetch.fetch_cached_or_new`. Falls back to `verify=False` for park sites with old cert chains (parks.or.jp).
3. **Extract** — three layered approaches because Tokyo has a unified template, the others do not:
   - `parklife/scrapers/tokyo.py` — pulls `花の見ごろ` blocks from the TMG template (1 scraper covers 137 parks).
   - `scripts/extract_tokyo_animals.py` + `scripts/scrape_subpages.py` — narrative-text mining: tokenise katakana, validate via Wikipedia normalizer, accept anything the NORMALIZER says is animalia/plantae/fungi. Same approach reused for all prefectures via `scripts/extract_kanagawa_pages.py`.
   - `scripts/inaturalist.py` — geographic enrichment via iNaturalist's `/observations/species_counts`, filtered by 8 iconic taxa (birds, mammals, reptiles, amphibians, insects, arachnids, molluscs, fish). The single biggest data source for non-plant species.
4. **Normalize** (`parklife/normalize/`, populates `species` + `species_alias`):
   - `wikipedia.lookup_with_cache` queries the JA Wikipedia API (taxobox-aware regex). ~83% hit rate on common names. Cached per-name under `data/cache/wikipedia/`. Includes `taxon_group → kingdom` fallback because many animal taxoboxes use templates that hide the plain "動物界" string.
   - `data/manual_species.json` is the curated fallback for names without a JA Wikipedia article (mostly cultivars, hybrids, common-word disambig pages).
   - `scripts.repair_kingdoms` retroactively fills `kingdom` for species whose `taxon_group` implies it.
   - `scripts.backfill_observations` joins `observation.raw_name` → `species_alias.species_id` once aliases are resolved.

### Source-page coverage by prefecture

The Tokyo CMS gives strong flora data (花の見ごろ); everything else is heterogeneous narrative text. **iNaturalist closes the gap** for animals across all four prefectures — its species_counts endpoint per geographic radius works regardless of the park's website structure.

> **Park count: the four prefectures originally seeded 209 parks; `scripts/p13_seed.py` (国土数値情報 都市公園 P13) expanded this nationwide.** Milestones: 461 (4 Kanto prefs, ≥5 ha biodiversity types) → **2,412 (all 47 prefectures, 2026-06-20)** → **3,082 (2026-06-25, added 地区公園 type-3 ≥5 ha)**. The P13 filter is now env-configurable: `P13_KDP` (comma-separated 公園種別 codes; default `4,6,9,11,14`), `P13_SUFFIX` (output `data/seeds/<pref>-<suffix>.json`, keeps originals untouched), `P13_DEDUP_M` (default 1 km, was 500 m), `P13_MIN_AREA_M2`. The 地区公園 tier was added via `P13_KDP=3 P13_SUFFIX=p13ext .venv/bin/python -m scripts.p13_seed all`. The per-prefecture figures below describe the **original 209** website-scraped parks; all P13 additions get their species purely from iNat/GBIF/eBird by geographic radius, not from website scraping. Occurrence data for ALL parks is now dominated by **GBIF > iNaturalist > eBird** — see `scripts/{gbif,ebird}.py`. **Evidence tiers (`observation.evidence_tier` / `park_species.evidence_tier`):** the radius/scrape sources are `'onsite'`; `scripts/gbif_admin.py` recovers GBIF's coordinate-less museum specimens (~66% of JP beetle records, discarded by the `hasCoordinate=true` radius query) by matching their romaji 市区町村 to parks (`parklife/admin_match.py`, fail-closed gates), tagged the weaker `'admin:municipality'`. `dedupe` keeps the strongest tier per pair (onsite > admin); `api.park_*.n` counts **onsite only** (honest headline); the webapp hides admin rows behind an opt-in "含周边区域记录" toggle with a `📍市区町村` badge. Same "evidence over coverage / absence≠negation" ethos as parking — a region-level record is real but explicitly weaker, never silently mixed into on-site presence.

- **Tokyo (137)** — uniform template. 132/137 parks have data (96%).
- **Kanagawa (27)** — only nanasawa has structured catalogs; iNat covers the rest. 24/27 (89%).
- **Chiba (13)** — pref site is narrative-only; 指定管理者 sites still 403 on default TLS. iNat fills 11/13 (85%).
- **Saitama (32)** — fragmented operator domains; one parks.or.jp subdomain uses an old cert chain (handled by `verify=False` fallback). iNat covers 31/32 (97%).

When asked to "scrape more X," consider whether iNat already has it — `query species --group X` is the quickest check.

### The normalization problem

Two invariants that the pipeline depends on:

- **Never lose the original name.** `observation.raw_name` always preserves what the page said; `species_id` is the resolved link, nullable.
- **Aliases are first-class.** `species_alias` maps any (raw_name, lang) → species. Two distinct katakana names that resolve to the same Latin binomial share one `species` row (synonyms collapse). New scrapers add aliases; they don't mutate species rows. Re-running normalization is cheap and reversible.

Don't match species by string equality across parks — always go through `species_alias`.

A note on disambiguation: common-word entries (フジ, ボケ, モミジ, サクラ) often hit Wikipedia disambiguation pages. These are routed to the user-facing default species via `data/manual_species.json` (e.g. フジ → *Wisteria floribunda*, the noda-fuji). When in doubt, prefer the species most commonly meant in a Japanese park context.

### Provenance vs deduplication: `observation` vs `park_species`

- **`observation`** is append-only. Each row records a single sighting from a single source (TMG flora list, iNat species_counts, iNat monthly query, etc.). Rows for the same park-species pair from different sources coexist — that's how we keep provenance. `where ソメイヨシノ` against `observation` would show duplicates.
- **`park_species`** is a derived table built by `scripts.dedupe`: one row per (park_id, species_id) with `months_bitmap` OR'd across sources, and `raw_names` / `location_hints` / `characteristics` joined. Also carries `evidence_tier` (strongest of onsite/admin:municipality) and `abundance` (max source-reported obs_count on the onsite rows — the perception/ranking signal). This is what queries and exports should consume by default. **dedupe drops non-perceivable microbes** (bacteria/viruses/archaea always; protozoa/chromista only when they lack a JA vernacular — so slime molds/seaweeds stay); the raw rows remain in `observation` for provenance.

Rule of thumb:
- "How did we know X is at park Y?" → query `observation` (provenance).
- "Is X at park Y, and when?" → query `park_species` (clean answer).

Anytime `observation` changes (new ingestion, normalization, kingdom-repair, manual fix), re-run `scripts.dedupe` before exporting.

### Months as a bitmap

`observation.months_bitmap` packs Jan–Dec into 12 bits (bit 0 = Jan). `NULL` means year-round or unknown — distinguish these only if a site explicitly says so. Use bitwise ops in SQL for "which species are seen in month N" queries.

### Parking classification: evidence over coverage

`park.has_parking` is **3-state — 1 (public parking) / 0 (none or restricted-only) / NULL (unknown)** — and `park.parking_source` records *how* we know (the tier). All rules live in **`parklife/parking.py` (single source of truth)**; the three `scripts/*_parking` passes just feed it cached text / OSM results. Never re-implement the regexes elsewhere.

Two invariants that make the labels trustworthy at nationwide scale:

- **Absence is not negation.** "No `amenity=parking` within 300 m in OSM" and "no page mentions 駐車場" both mean **unknown (NULL)**, never a confident 0. OSM under-mapping in Japan is indistinguishable from a real lack of parking, so an OSM miss must leave the row re-checkable. Only explicit **text** phrasing (駐車場なし／ありません) or restricted-only access yields `has_parking=0`. Before this rule, >half of all "no parking" labels were really just unmapped parks — a confident-but-wrong negative that would have multiplied across the other 43 prefectures.
- **Restricted ≠ public.** 団体予約のみ／障害者専用／観光バス専用 parking is tagged `text:restricted` and collapses to `has_parking=0` ("公開駐車場あり" は満たさない).

Source tiers, high→low confidence: `text:negative` · `text:restricted` · `text:positive` · `text:mention` · `osm:present` · `osm:absent`(→NULL) · `manual` · `unknown`(→NULL). When expanding, run the three parking passes (see Commands) on the new parks; rows that come back NULL are honestly unknown, not silently "no parking". One-off `scripts/probe_*_parking.py` are superseded exploratory scripts — ignore them.

## Conventions

- One scraper module per park-management system, not per individual park. Most prefectures have a unifying CMS or association site; exploit that.
- All fetched HTML is cached under `data/raw/<prefecture>/<park-slug>/<sha>.html` and gitignored. Scrapers should re-parse the cache rather than re-fetching during development.
- Be polite: 1 req/sec default, set a descriptive User-Agent, respect `robots.txt`. Many target sites are run by small municipal teams.
- Japanese text is UTF-8 throughout. SQLite handles this natively; don't add encoding shims.
- **Photo caches store only the fields consumed, not whole API responses.** The photo-selection scripts (`collect_species_photos.py`, `park_species_photo.py`) read ~8 fields per record, but the iNat/GBIF endpoints return 60+; caching the full payload once bloated `data/cache/inat_photos` to 21 GB (95× waste) and `data/cache/gbif` to 7.7 GB. Writers now slim on write via `scripts.prune_caches.slim_payload` / `slim_gbif` (the field whitelists live there — extend them if a reader needs a new field). Never re-introduce a raw-response cache. All photo URLs are already baked into `species_photo` / `park_species_photo`, so the caches are pure re-run artifacts.

## Maintenance / disk hygiene

`data/cache/` is regeneratable and gitignored but grows unbounded; reclaim it with:

```bash
.venv/bin/python -m scripts.prune_caches report                 # cache + backup sizes
.venv/bin/python -m scripts.prune_caches slim-inat [--dry-run]  # shrink inat_photos in place (~95×), keeps re-runnable
.venv/bin/python -m scripts.prune_caches slim-gbif [--dry-run]  # shrink gbif occurrence cache in place (~7×)
.venv/bin/python -m scripts.prune_caches trim-backups --keep 1  # delete all but newest N DB backups (kept-file = last by filename, not date)
```

Slimming is idempotent (re-slimming a slim file is a no-op) and lossless for every field the pipeline reads.

## Operational notes

- Token budget: when API limits hit, pause and wait — do not switch to a smaller model or skip parks. The collection is incremental, so resuming from `source.fetched_at` is straightforward.
- Scope creep risk: 国営 (national) parks, 区立 (ward) parks, 市立 (city) parks all exist and are huge. Stay within the four prefectures' top-level managed parks until the v1 schema is proven.
