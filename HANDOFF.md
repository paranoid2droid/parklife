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

Project is in maintenance + enrichment mode. Core pipeline shipped: 209 parks, **7,137 species, 94k observations**. Code + Pages site at <https://github.com/paranoid2droid/parklife>; demo published from `docs/` at <https://paranoid2droid.github.io/parklife/>. Active session 2026-04-30: shipped TODO #6 (demo checkbox+sort) and TODO #4 GBIF main pass; identified follow-up cleanups (near-duplicate species merge, microbial-kingdom display policy, `gbif_vernacular` long-running pass).

## In progress

*(none — nothing mid-flight at handoff time)*

## Blocked / waiting

- **eBird API key** — user needs to register at <https://ebird.org/api/keygen> before TODO #4 can start. Free, instant.
- **User decisions still open**: default state of taxon-checkbox filter on demo (all-checked vs. localStorage memory) — see TODO #5.

## Next up

Mirror of the user's prioritized TODOs (recorded 2026-04-30). Pick from the top unless the user redirects.

1. **Expand park coverage beyond 都立/県立** — current 209 misses 国営/区立/市立/自然観察園. Discuss difficulties before scraping. Sources: 国土数値情報, Wikipedia 都県別公園一覧, OSM `leisure=park`.

2. **Reduce parking-unknown count (71 NULL)** — investigate per-page why classifier misses. Constraint: `団体予約のみ可` ≠ `公開駐車場あり`; must distinguish before loosening matching.

3. **Demo: multi-language toggle** — order English → 簡体 → 繁体. `common_name_en` exists for ~3431 species (GBIF). **zh coverage is still thin** (337 aliases total, ~5% of species) after both GBIF vernaculars and Wikipedia langlinks. Two unexplored options for densifying zh: (a) Wikidata Q-IDs → labels in zh-Hans/zh-Hant (most thorough), (b) harvest zh.wikipedia taxoboxes by scientific name. Decide before committing UI work.

4. **External occurrence-data enrichment** (Gap #10 in SUMMARY.md), priority order:
   - **eBird** (birds, highest value) — needs API key, env var `EBIRD_API_KEY`, cache under `data/cache/ebird/`. Endpoint: `data/obs/geo/recent` (lat/lon + radius_km).
   - **GBIF** ✅ both passes shipped: occurrence (2026-04-30, 45k obs, +4k species) and vernacular (2026-05-01, +3431 en / +170 zh aliases). Chinese coverage is thin in GBIF — TODO #3 will need Wikipedia zh interlanguage links to densify.
   - **いきものログ** (env.go.jp) — Japan MoE, all taxa, gov-curated. No public API; bulk CSV ingest. Highest data quality, lowest convenience.
   - Skipped (evaluated): FishBase, MushroomObserver, Pl@ntNet.

5. **Demo: data-source filter** — add a top-bar selector ("全て / 公園官网 / iNaturalist / GBIF / iNat+GBIF") so users can scope which provenance they're looking at. Useful because 97% of observations come from geographic enrichment (iNat 50% + GBIF 48%), only ~2% from the original park-website scrape. The `observation.location_hint` field already tags this; export needs to surface per-pair source set into `parklife.json` so the front-end can filter without re-querying. Estimate: ~1 hour. Recorded 2026-04-30.

6. **Demo: checkbox-filtered species list + sort controls** — ✅ shipped 2026-04-30. Sort options: 出現公園数 / 名称（日本語）/ 学名. Group checkboxes + sort persisted via localStorage (`parklife.hiddenGroups`, `parklife.speciesSort`).

   **Follow-up** (decided 2026-04-30, not yet done): better frequency metric. Currently sort uses `sp.n` = global count of parks containing the species. Two improvements queued:
   - Acquire **per-park observation count** (would require adding a `park_species.obs_count` column or surfacing existing `observation` counts to the export) — most accurate.
   - Until that exists, **constrain the `sp.n` fallback to geographically nearby parks** so a 関東-wide common species doesn't dominate over a locally-clustered one. Define "nearby" via lat/lon radius (e.g. 30 km) or by prefecture.
   - When multilingual support (TODO #3) lands, name sort should switch to the active UI language's name field, not always Japanese.

## Recent sessions

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
