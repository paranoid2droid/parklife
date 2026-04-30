# Long-running batch log

Started 2026-04-28. User away ~10 hours; will continue until extra-usage budget depleted.

## Goals (priority order)

1. Find animal data (esp. birds) missed in initial Tokyo pass
2. Refetch promising sub-pages (鳥類園, 自然文化園, ビジターセンター)
3. Geocode all 209 parks (Nominatim)
4. iNaturalist per-park species enrichment (real observed birds/mammals/insects)
5. Re-normalize new species names
6. LLM-assisted extraction for Kanagawa/Saitama heterogeneous sites
7. Final stats + JSON export

## Progress

### Phase A — animal mentions in Tokyo park main pages
- 18 parks had `野鳥/サンクチュアリ/etc.` headings with narrative species lists
- Tokenized + Wikipedia-validated → **63 new observations** in 10 parks (oizumi-chuo +19, shakujii +10, mukojima +8, rinshinomori +8, sakuragaoka +4, etc.)
- Discovered + fixed: Wikipedia-resolver was missing `kingdom` for many animal articles because they use `{{Taxobox}}` templates instead of plain "動物界" text. Added `taxon_group → kingdom` fallback. 43 existing species rows + 70 cache files repaired.

### Phase B — sub-pages and PDFs
- Filtered for park-specific sub-page anchors: 21 parks
- Targets included `creature/`, `news/nature/`, bird-list PDFs (kyu-shiba-rikyu, zenpukuji)
- Installed `pypdf` for PDF text extraction
- **142 new observations** in 9 parks: komine +64, ogasawara +38 (Bonin endemics!), kyu-shiba-rikyu +14, oyamadairi +14

### Phase C — geocode
- Nominatim (OSM) at 1 req/sec
- 188/205 parks geocoded (≈92% hit rate)
- Cached per park under `data/cache/geocode/`

### Phase D — iNaturalist
- Endpoint: `/v1/observations/species_counts` filtered by lat/lon + iconic_taxa
- 8 taxa: Aves, Mammalia, Reptilia, Amphibia, Insecta, Arachnida, Mollusca, Actinopterygii
- Quality grade: research only; locale=ja for Japanese vernaculars
- 192 parks × 8 taxa = 1,536 API calls; ≈25 min wall time
- Inserted observations: **+23,470** (1,832 → 25,302)
- Birds: 16 → 230 species (~93k extant Japanese bird species sample now ~25%)

### Phase E — re-normalize
- 27 residual katakana tokens caught from Phase F (after iNat enrichment exposed new aliases)
- All resolved cleanly via Wikipedia ja API

### Phase F — Kanagawa/Saitama/Chiba page extraction
- 72 parks scanned for editorially-curated species mentions
- 22+3 (after SSL fallback) parks added new observations (84+3 obs)
- Several parks.or.jp had old cert chains; added `verify=False` retry to fetch helper

### Phase G — final exports
- **`data/export/parklife.json`** — single-file portable snapshot
- **`data/export/park_species.ndjson`** — streaming-friendly tuples
- **`data/export/parks_md/<prefecture>/<slug>.md`** — 209 per-park markdown pages
- **`data/export/parks_md/INDEX.md`** — index sorted by prefecture and obs count

### Phase H/I/J — monthly seasonality enrichment (iNaturalist again)
- For each park × taxon × month: query species_counts with `month` filter
- Bird (taxon 3):    192 parks × 12 months = 2,304 calls
- Insect (47158):    192 parks × 12 months = 2,304 calls
- Mammal (40151):    192 parks × 12 months = 2,304 calls
- Updates `months_bitmap` on existing iNat rows; inserts new rows for species
  that only appear in a specific month (e.g., winter migrants)
- Adds ~23,500 observation rows mostly from new month-specific species

### Phase H+ — manual coordinates + repeat enrichment for 17 parks
- 17 parks Nominatim missed (Mt Takao, Bonin, Hachijo, Oshima, Okutama, etc.)
  got manually-set coordinates in `data/manual_coords.json`
- Re-ran iNaturalist + monthly for these high-biodiversity sites
- Now **209/209 parks have data** (100% coverage)

### Final tallies (after all phases — 2026-04-28 evening)
- Parks total / with data:  209 / 209  (100%)
- Species:                  2,947 (2,913 with scientific name)
- Observations:             48,833 (48,831 linked to species)
- Aliases (search keys):    7,551

| Prefecture | Obs | Parks with data |
|---|---|---|
| Tokyo    | 39,023 | 137 / 137 |
| Kanagawa |  5,371 |  27 / 27  |
| Saitama  |  3,437 |  32 / 32  |
| Chiba    |  1,002 |  13 / 13  |

| Taxon group | Species | Obs |
|---|---|---|
| insect    | 1,593 | 26,187 |
| bird      |   249 | 13,130 |
| arachnid  |   115 |  2,628 |
| plant     |   423 |  1,615 |
| fish      |   155 |  1,418 |
| reptile   |    28 |  1,329 |
| mollusk   |   177 |  1,198 |
| mammal    |    42 |    576 |
| amphibian |    19 |    420 |
| herb      |    57 |     99 |
| tree      |    26 |     75 |
| shrub     |    24 |     71 |
| vine      |     2 |     20 |

