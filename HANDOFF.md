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

Project is in maintenance + enrichment mode. Core pipeline shipped: 209 parks, ~7k species. **Repo consolidated 2026-04-30**: code + Pages site now live in <https://github.com/paranoid2droid/parklife>; demo published from `docs/` at <https://paranoid2droid.github.io/parklife/>. The old `parklife-demo` repo is frozen (no longer updated). User is waiting on quota reset before tackling the queued TODOs.

## In progress

*(none — nothing mid-flight at handoff time)*

## Blocked / waiting

- **eBird API key** — user needs to register at <https://ebird.org/api/keygen> before TODO #4 can start. Free, instant.
- **User decisions still open**: default state of taxon-checkbox filter on demo (all-checked vs. localStorage memory) — see TODO #5.

## Next up

Mirror of the user's prioritized TODOs (recorded 2026-04-30). Pick from the top unless the user redirects.

1. **Expand park coverage beyond 都立/県立** — current 209 misses 国営/区立/市立/自然観察園. Discuss difficulties before scraping. Sources: 国土数値情報, Wikipedia 都県別公園一覧, OSM `leisure=park`.

2. **Reduce parking-unknown count (71 NULL)** — investigate per-page why classifier misses. Constraint: `団体予約のみ可` ≠ `公開駐車場あり`; must distinguish before loosening matching.

3. **Demo: multi-language toggle** — order English → 簡体 → 繁体. `common_name_en` mostly exists; Chinese names via Wikipedia zh interlanguage links or GBIF vernacularNames (overlaps with TODO #4).

4. **External occurrence-data enrichment** (Gap #10 in SUMMARY.md), priority order:
   - **eBird** (birds, highest value) — needs API key, env var `EBIRD_API_KEY`, cache under `data/cache/ebird/`. Endpoint: `data/obs/geo/recent` (lat/lon + radius_km).
   - **GBIF Occurrence API** (<https://api.gbif.org>, no key) — aggregates iNat + eBird + museum specimens. Cross-check + rare taxa. Also use `vernacularNames` for TODO #3.
   - **いきものログ** (env.go.jp) — Japan MoE, all taxa, gov-curated. No public API; bulk CSV ingest. Highest data quality, lowest convenience.
   - Skipped (evaluated): FishBase, MushroomObserver, Pl@ntNet.

5. **Demo: checkbox-filtered species list + sort controls** — ✅ shipped 2026-04-30. Sort options: 出現公園数 / 名称（日本語）/ 学名. Group checkboxes + sort persisted via localStorage (`parklife.hiddenGroups`, `parklife.speciesSort`).

   **Follow-up** (decided 2026-04-30, not yet done): better frequency metric. Currently sort uses `sp.n` = global count of parks containing the species. Two improvements queued:
   - Acquire **per-park observation count** (would require adding a `park_species.obs_count` column or surfacing existing `observation` counts to the export) — most accurate.
   - Until that exists, **constrain the `sp.n` fallback to geographically nearby parks** so a 関東-wide common species doesn't dominate over a locally-clustered one. Define "nearby" via lat/lon radius (e.g. 30 km) or by prefecture.
   - When multilingual support (TODO #3) lands, name sort should switch to the active UI language's name field, not always Japanese.

## Recent sessions

### 2026-04-30 (Claude) — TODO #5 shipped
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
