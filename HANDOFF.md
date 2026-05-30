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

Project is in maintenance + enrichment mode. **461 parks / 9,579 visible species / 126,405 visible park-species pairs** as of 2026-05-30. Code + Pages site at <https://github.com/paranoid2droid/parklife>; demo published from `docs/` at <https://paranoid2droid.github.io/parklife/> (current export 37.0 MB). **3,219 species** have curated profiles in ja/en/zh/zhT (12,872 rows). **np≥5 tier is 100% covered** (2026-05-30, A54–A67 sweep, +318 profiles; np≥6 cleared 2026-05-29, np≥7 same day, np≥8 on 2026-05-28). P13 official-URL coverage **443/461 parks (96%)** — 18 small 緑地/河川敷 stay `__no_url__`. Parking: 122 OSM-only + 339 text-confirmed.

**DB integrity (2026-05-29)**: 0 orphan rows across alias/profile/photo/observation; 0 dead parks; 0 dupe scientific_names; 0 iNat-id collisions. 2 NULL-species observations remain (descriptive labels, harmless). 6 ASCII-prefix common_name_ja: 2 with no iNat ja-name, 4 without inat_taxon_id (Sawara homonym resolved 2026-05-27 via kanji disambig `サワラ（椹）` / `サワラ（鰆）`). Remaining NULL-sci visible placeholders (2026-05-29): 23 generic-category words (スイレン属 np=3, ドングリ/ヤエザクラ/コオロギ/トンボ/カエル/バッタ np≤2, rest np=1 — シダ類/タンポポ/カエデ/エリカ/ダリア etc.) — all low np broad categories, not worth bespoke fixes. The two clear-junk non-taxa (コミュニケーション, タケノコ) were deleted 2026-05-29; the resolvable sakura cultivars (カワヅザクラ→558, コブクザクラ, ジンダイアケボノ) were given scientific_names.

## In progress

**species_profile np=4 tier sweep (A68–A80 done, 3,522 profiled / 2026-05-30).** 54 np=4 candidates remain. Continue alphabetically: re-run the np=4 query (see Active #1), take the next ~23 by `s.scientific_name`, write `/tmp/profile_batchA81.py`, then seed→export→`cp`→commit→push. Last done: Shaka atrovittatus (next batch starts at Sialis / センブリ属 — note: genus-level entry, alderfly). ja-name DB fixes applied this tier: `Acer japonicum` (dropped romaji annotation), `Allium chinense` rakkyo→ラッキョウ, `Phedimus aizoon` 麒麟草→キリンソウ, `Phillipsia domingensis` 肉厚紅皿茸→ニクアツベニサラタケ (all local DB only).

## Blocked / waiting

*(none currently)*

## Next up

Active TODOs only. Shipped items are pruned to git log + Recent sessions. Pick from the top unless the user redirects.

### Active

1. **species_profile curation — np≥5 DONE. Continue from A68 into np=4 tier** *(at 3,219 / 2026-05-30)*
   - **Sidecar workflow** (`data/species_profiles_extra.json`): every entry MUST include `common_name_en` (if DB has NULL or generic) + `aliases.{zh-Hans}` (if DB lacks it) alongside the 4-language profile. zhT auto-derived via OpenCC. See `BATCH_TEMPLATE.md` at repo root.
   - **Query next batch** — change `np >= 5` to `np >= 4` (then 3, 2, …):
     ```sh
     sqlite3 data/parklife.db "SELECT s.scientific_name, s.common_name_ja, COUNT(DISTINCT ps.park_id) AS np FROM species s JOIN park_species ps ON ps.species_id=s.id LEFT JOIN species_profile sp ON sp.species_id=s.id WHERE sp.species_id IS NULL AND s.scientific_name IS NOT NULL AND s.common_name_ja IS NOT NULL AND s.common_name_ja != '' AND SUBSTR(s.common_name_ja,1,1) NOT BETWEEN 'A' AND 'Z' AND s.common_name_ja NOT LIKE '%・%' AND s.common_name_ja NOT LIKE '%（%' GROUP BY s.id HAVING np >= 4 ORDER BY np DESC, s.scientific_name LIMIT 30;"
     ```
   - **Typo guard**: when hand-writing `zh-Hans` aliases, double-check for garbled chars before running — A47/A58 had to be fixed (大阪绿步甲, 近缘牙甲, 蚊子草). A bad alias inserts into `species_alias`; purge with `DELETE FROM species_alias WHERE raw_name='<bad>';` then re-seed.
   - **Per-batch loop**: write `/tmp/profile_batchN.py` → run → `.venv/bin/python -m scripts.seed_species_profiles` → `scripts.export_html` → `cp data/export/index.html docs/index.html` → commit every 1–2 batches.
   - **np≥9 cleanup history**: A24 cleared romaji-rescued high-np (ヤハズエンドウ et al). A25–A28 cleared the regular np=9 species (90 entries). A29 closed the last 2 edge cases (Malus toringo had romaji ja `ko-nashi` → fixed to ズミ in DB; Macrogerris is a subgenus treated as ツツジ属 was).
   - **np=8 cleanup history (2026-05-28, A30–A37)**: cleared 144 species across 8 batches; sidecar backfilled ~74 common_name_en + ~40 zh-Hans aliases. Demo 34.8 → 35.2 MB.
   - **np=7 cleanup history (2026-05-29, A38–A44)**: cleared all 158 np=7 species across 7 batches (Acanthosoma→Vibidia); ~75 common_name_en + ~38 zh-Hans aliases backfilled. Demo 35.2 → 35.6 MB.
   - **np=6 cleanup history (2026-05-29, A45–A53)**: cleared all 207 np=6 species across 9 batches (Acanthochitona→Weigela) + 2 stragglers; also fixed placeholder ja-name `Bucephala albeola` カモ→ヒメハジロ in DB. Demo 35.7 → 36.2 MB.
   - **np=5 cleanup history (2026-05-30, A54–A67)**: cleared all 318 np=5 species across 14 batches (Abelia→Zaranga). Demo 36.2 → 37.0 MB. Note `R.arborea`/シャクナゲ has a mangled sci name (treated as genus-level rhododendron profile) — leave as-is.
   - **Remaining tiers**: np≥4 → ~450, np≥3 → ~900, all visible → ~4,000. Batch of 22–23 costs ~12–16k tokens.

2. **Periodic latent-data maintenance** *(run after every major ingestion; cheap)*
   - `.venv/bin/python -m scripts.merge_duplicate_species` — collapses synonym pairs sharing one `inat_taxon_id`; NULLs bogus tids covering many unrelated species. Last run 2026-05-26 (-55 dups, 6 bogus tids NULLed).
   - `.venv/bin/python -m scripts.fix_romaji_ja_names` — rescues ASCII-prefix `common_name_ja` placeholders via iNat `locale=ja`; preserves romaji form as ja alias. Last run 2026-05-26 (62 renamed). New ingestion (especially iNat) re-introduces these.
   - Both have `--dry-run`; run after eBird/GBIF/iNat enrichment passes.

3. **いきものログ ingest (env.go.jp)** *(not started, low-medium priority)*
   - Japan MoE platform, all taxa, gov-curated. No public API; bulk CSV ingest. eBird + GBIF + iNat already cover the bulk of what's reachable; this would add rarer / locally-restricted records and validate edge cases.

4. **TMG SPA parking parse via scrapling** *(deferred, low priority)*
   - 32 `tokyo-park.or.jp/park/<slug>/index.html` URLs are JS-rendered SPA shells. Current `scripts/extract_parking.py` + `scripts/reclassify_parking.py` fail on them (stub returns 0 text). Would need `scrapling install` (~200 MB Chromium). Not worth the dependency for 32 parks alone.

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

- **Photo gallery** *(post-`87f5553`, ~90.5% visible-species coverage)*
  - ~917 visible species still have no photo. Periodically re-run `scripts.collect_species_photos` (broad fallback) as iNat acquires more.
  - Truncate verbose Commons `extmetadata.Artist` HTML to first author when "Multiple contributors" lists appear.
  - Add Flickr / GBIF media as a 3rd hero source for taxa with neither iNat nor Commons coverage.

- **Species sort: regional `sp.n` tiebreaker** *(post-`a85c1ba`)*
  - Current `freq` sort: `pair.oc` desc primary, `sp.n` desc tiebreaker. When two species both have 1 record at the selected park, global spread tiebreaker favors 関東-wide commons over locally-clustered species. Precomputed `sp.regional_n` per (species, prefecture) would fix this; defer until a user complaint surfaces.

- **`data/parklife.db.bak*` cleanup** — 7 backups, ~738 MB total local-only. Safe to keep 1 recent good snapshot; older ones (`.bak`, `.bak2`, `.bak3` from 5/18–5/23) can go. Not gitignored issue since `data/parklife.db*` is excluded.

## Recent sessions

### 2026-05-30 (Claude) — np=4 tier A80 (3498→3522, +24; committed + pushed)
- Batch A80 swept Pteris → Shaka. Highlights: Pied Avocet (反嘴鹬), Five-leaf Azalea (シロヤシオ/五叶杜鹃), Wineberry (エビガライチゴ), Green Brittlegill (アイタケ/变绿红菇, edible russula), Fortune's Saxifrage (ダイモンジソウ, "大"-character flower), Wild Radish, Japanese Cedar Longhorn, red-gilled aeolid.
- Verified Sabia conica/キクスズメ is a mollusk (hoof snail) via taxon_group before writing. Demo 37.8 → 37.9 MB. 54 np=4 candidates remain. Next A81 from Sialis.

### 2026-05-30 (Claude) — np=4 tier A79 (3474→3498, +24; committed + pushed)
- Batch A79 swept Pinellia → Pteraeolidia. Highlights: Indianmeal Moth (印度谷螟), Moss Rose (松叶牡丹), Blue Dragon Nudibranch (蜈蚣鳃海蛞蝓), Ruler Damselfly (モノサシトンボ), Chinese Cinquefoil (委陵菜), 3 holly ferns (イノデ属), leafless haircap moss.
- Demo stable 37.8 MB. 78 np=4 candidates remain. Next A80 from Pteris pseudosefuricola.

### 2026-05-30 (Claude) — np=4 tier A78 (3450→3474, +24; committed + pushed)
- Batch A78 swept Oryctolagus → Pilosabia. Highlights: European Rabbit, Tree Peony (牡丹), Short-tailed Albatross (アホウドリ, endangered), Blue Bat Star (海燕), Aizoon Stonecrop (費菜), boxfish, lantern slime mould.
- 2 ja-name DB fixes (local-only): `Phedimus aizoon` 麒麟草→キリンソウ, `Phillipsia domingensis` 肉厚紅皿茸→ニクアツベニサラタケ.
- Demo 37.0 → 37.8 MB. 102 np=4 candidates remain. Next A79 from Pinellia tripartita.

### 2026-05-30 (Claude) — np=5 tier cleared: A54–A67 sweep (2901→3219, +318; committed + pushed)
- 14 batches (A54–A67) alphabetically swept Abelia → Zaranga; np≥5 now 0 candidates (verified).
- Highlights: Japanese skink, Tanuki-zone fauna, giant flying squirrel, Baer's Pochard + Ferruginous Duck + Bufflehead + Brant + Shelduck (rare ducks), Star Magnolia, water caltrop relatives, waterwheel plant (carnivorous), Dead Man's Fingers, many shore molluscs/fish/hermit crabs.
- Fixed 3 zh-Hans typos mid-sweep (大阪绿步甲, 近缘牙甲, 蚊子草). `R.arborea`/シャクナゲ kept as genus-level rhododendron (mangled sci name, left as-is).
- Demo 36.2 → 37.0 MB. **np≥5 coverage 100%.** Next: np=4 tier (~450 candidates).

### 2026-05-29 (Claude) — np=6 tier cleared: A45–A53 sweep (2694→2901, +207; committed + pushed)
- 9 batches (A45–A53) alphabetically swept Acanthochitona → Weigela; np≥6 now 0 candidates (verified). +2 stragglers (ヌマムツ, オカヒジキ) in A53b.
- Highlights: Tanuki-adjacent fauna, Christmas Rose, Poison Hemlock (toxic), panthercap + destroying-angel Amanitas (toxic), Crested Kingfisher, Japanese Scops Owl, Laysan Albatross, Japanese Hare, Rugosa Rose, water caltrop, mistletoe, sea hibiscus, razor clam, turban shell.
- Fixed placeholder ja-name `Bucephala albeola` カモ→ヒメハジロ (DB UPDATE, local-only). Fixed 2 zh-Hans typos mid-sweep (大阪绿步甲, 近缘牙甲).
- Cumulative ~110 common_name_en + ~50 zh-Hans aliases backfilled. Demo 35.6 → 36.2 MB. **np≥6 coverage 100%.**

### 2026-05-29 (Claude) — np=7 tier cleared: A38–A44 sweep (2536→2694, +158; commits this session)
- 7 consecutive batches alphabetically swept Acanthosoma → Vibidia; np≥7 now 0 candidates remaining (verified).
- **A38** (+24): Acanthosoma→Buxus. Honshu Maple, Grey Burrowing Snake (Achalinus), Many-sepal anemone, Snake Amanita (toxic).
- **A39** (+24): Calidris→Eleutherococcus. Ruff, Taiwan Cherry + Kawazu-zakura cultivar, Strawberry conch, Green-eyed Robber Fly.
- **A40** (+24): Endotricha→Lepista. Harlequin Duck, Silver Carp, Fall Webworm, Festive Sea Slug (Aoumiushi), Blewit.
- **A41** (+24): Lichenophanes→Ophioglossum thermale. Tanuki (Nyctereutes), Dawn Redwood, Tallow tree, Sword fern, two adder's-tongue ferns.
- **A42** (+24): Ophioglossum vulgatum→Rattus. Red Phalarope, Moss-pink, Samurai slave-making ant (Polyergus), Flower crab, Rapa whelk.
- **A43** (+24): Rondibilis→Sympetrum. Rosalia batesi (iconic azure longhorn), Pussy willow, Korean stewartia, Red-veined Darter.
- **A44** (+14): Tachycines→Vibidia CLOSEOUT. Greenhouse Camel Cricket, Baldcypress, Horned Turban (Sazae), 12-Spot fungus-eating ladybird.
- Cumulative sidecar backfills ~75 common_name_en + ~38 zh-Hans aliases. Demo 35.2 → 35.6 MB. **np≥7 coverage 100%.**

### 2026-05-29 (Claude) — data-quality cleanup sweep (no commit-tracked DB; manual_species.json + docs re-exported)
- **Bufo fragmentation fixed**: `Bufo japonicus` (id=9929, romaji ja-name "Nihon Hikigaeru", np=84, no tid) was a split-off dup of `Bufo formosus`/アズマヒキガエル (id=820). iNat treats "Bufo japonicus" as a deprecated name split into formosus (Kanto) + praetextatus (W.Japan). 820 already held 92 "Bufo japonicus" raw obs via its sci alias → merged 9929→820 (now 176 + 353 obs). Romaji entry gone.
- **3 sakura cultivars resolved** (were NULL-sci): カワヅザクラ (id=106, ヅ-variant) merged into existing カワズサクラ (id=558, `Cerasus × kanzakura 'Kawazu-zakura'`); コブクザクラ (id=175) → `Cerasus 'Kobuku-zakura'`; ジンダイアケボノ (id=234) → `Cerasus × yedoensis 'Jindai-akebono'`. All 3 added to `data/manual_species.json` for future-proofing.
- **2 non-taxa deleted**: コミュニケーション (text-mining junk) + タケノコ (bamboo shoot, not a taxon).
- Net: species 9770→9766; null-sci visible 28→23; romaji-ascii visible species 6→5 (remaining 5 lack iNat ja-name/tid, documented). Ran `dedupe`, re-exported (35.2 MB), synced docs/. Integrity re-verified all-green.
- **Backups pruned**: 9 → 2 (kept `bak_pre_tsutsuji_sawara` 5/27 + `bak_pre_cleanup_20260529` today); freed ~742 MB.

### 2026-05-28 (Claude) — np=8 tier cleared: A30–A37 sweep (2371→2537, +144; commits `0067a12` → `cce7b66`)
- 8 consecutive batches (A30–A37) alphabetically swept Acer → Zoothera. Final batch A37 (12 entries) closed the tier; np≥8 now 0 candidates remaining.
- **A30** (`0067a12`, +22): Acer→Bassia. Greater White-fronted Goose, Tamagotake, Sweet Annie, Thale Cress, Kochia.
- **A31** (`cd39fed`, +22): Bristowia→Coprinellus. Sharp-tailed Sandpiper, Siberian Rubythroat, Japanese Serow, Eurasian Treecreeper, Peppery Bolete, Bamboo Borer.
- **A32** (`17d098d`, +22): Clytus→Eurema. Japanese Quail, Constable Butterfly, Chinese Grosbeak, Bird-dropping mimic Cyrtarachne, Tasmanian Blue Gum.
- **A33** (`004e6ca`, +22): Eutonia→Lactuca. Beefsteak Fungus, Witches' Butter, Senegal Tea, Asian Shore Crab, 13-spot Ladybird, Panicle Hydrangea.
- **A34** (`748a8fe`, +22): Laportea→Nippancistroger. Japanese Bell Cricket, Smallmouth + Largemouth Bass, Magic Lily, Southern Magnolia, Burgundydrop Bonnet, Japanese Green Hairstreak.
- **A35** (`6492684`, +22): Nipponobuprestis→Pyracantha. Masu Salmon, Crested Honey Buzzard, Russet Sparrow, Spangle Swallowtail, Japanese Bombardier Beetle, Misty Cherry, White-browed Laughingthrush.
- **A36** (`c7980f4`, +22): Rhantus→Tartessus. Floating Fern (Salvinia), Goat Willow, Ancient Murrelet, Hamabō Hibiscus, East Asian Swertia, Yellow Dung Fly.
- **A37** (`cce7b66`, +12): Ternstroemia→Zoothera closeout. Wakame, Crimson Glory Vine, Scaly Thrush, Mokkoku, Mulberry Tiger Longhorn.
- Cumulative sidecar backfills ~74 common_name_en + ~40 zh-Hans aliases. Demo 34.8 → 35.2 MB. **np≥8 coverage 100%.**

### 2026-05-28 (Claude) — np≥9 tier cleared: A25–A29 sweep (2279→2371, +93; commits `5a4f2fd` → `f3e7804`)
- **A25** (`5a4f2fd`, +22): Dichomeris→Matricaria. Highlights: Merlin, Tokyo Salamander, Glandirana reliquia frog, Geastrum+Lycoperdon fungi.
- **A26** (`07e5661`, +25): Echinolittorina→Palaemon. Highlights: 5 jewel/spittle/sesiid insects, Hiroses' damselfly Mortonagrion (Red List EN-IB), Tetrapanax planthopper, both Palaemon prawns.
- **A27** (`8efde9e`, +25): Parasa→Spicantopsis. Highlights: Phalaropus phalarope, Parmotrema lichen (air-quality indicator), Quercus dentata (kashiwa-mochi oak), Sphrageidus moth (with urticating hairs warning).
- **A28** (`a4cc515`, +18): Simulatacalles→Yezoterpnosia. Highlights: Copper Pheasant, Spring Cicada, Spotted Redshank, Mushak Cupid (recent invader from China).
- **A29** (`f3e7804`, +2): closeout. **Malus toringo had romaji ja `ko-nashi`** → fixed in-DB to `ズミ` (canonical), `ko-nashi` preserved as ja-romaji alias, mis-tagged `en`→`ja` alias corrected, pinyin `san ye hai tang` zh-Hans alias purged. Macrogerris (subgenus 亜属) profiled following ツツジ属 precedent.
- Cumulative: 8 batches over 2026-05-27/28, en backfills ~41 + zh-Hans alias backfills ~23. Demo 34.5→34.8 MB. **np≥9 coverage 99.9% → 100%.**

### 2026-05-27 (Claude) — ツツジ + Sawara: genus entry + homonym disambig (commit `d76b147`)
- ツツジ (id=270, was NULL-sci np=25): set `scientific_name='Rhododendron sp.'`, `common_name_ja='ツツジ属'`, `taxon_group=shrub`; added zh-Hans alias `杜鹃花属`. Existing `ツツジ` ja/ja-kana aliases preserved for resolver. **First time the schema uses genus-only `sci sp.` notation** — works fine with seed/export pipelines.
- Sawara homonym (Wikipedia-style kanji disambig): id=3417 tree → `サワラ（椹）`, id=588 fish → `サワラ（鰆）`. New ja/ja-kana aliases for both disambiguated forms. Wrongly-tagged `en`-lang `サワラ` alias on tree row dropped. `SKIP_IDS` guard in `fix_romaji_ja_names.py` kept (now dead code, but documents the regression risk).
- DB integrity unchanged; species/pairs totals stable at 9,583 / 126,491.

### 2026-05-26 (Claude) — system audit + merge_duplicate_species pass
- Integrity scan: 0 orphan rows across alias/profile/photo/observation; 0 dead parks; 0 dupe `scientific_name`; only 2 NULL-species observations (descriptive labels, harmless). Healthy.
- Ran `scripts.merge_duplicate_species` (hadn't been run in weeks): 6 bogus `inat_taxon_id` collisions (each shared by 13–32 unrelated species) NULLed; 55 legitimate synonym pairs/triples (Vitex agnus/agnus-castus, Botaurus sinensis/Ixobrychus sinensis, Anoplophora chinensis/malasiaca, etc.) collapsed. Visible species 9640 → 9583.
- HANDOFF restructured: Active list rewritten with 6 concrete items, periodic-maintenance task added as #2 (run `merge_duplicate_species` + `fix_romaji_ja_names` after every iNat/GBIF/eBird ingestion), Recent sessions trimmed from ~60 entries to ~15.

### 2026-05-26 (Claude) — romaji ja-name placeholder fix (62 species)
- New `scripts/fix_romaji_ja_names.py`: queries iNat `locale=ja` to recover canonical katakana for species whose `common_name_ja` was a romaji placeholder (`Yahazu-endo` → `ヤハズエンドウ`, `Oni-tabirako` → `オニタビラコ`, ...). 60 renamed; 2 sibling-typo duplicates merged via `merge_species_pair` (Paraprenanthes sororia/sorosia, Cephalotaxus harringtonii/harringtonia); 1 homonym (`Sawara` tree vs `サワラ` fish, id=3417) skipped via SKIP_IDS. Strips trailing `(広義)` for consistency with prior cleanup.
- These 60+ species were previously invisible to the profile-batch query (filter `SUBSTR(common_name_ja,1,1) NOT BETWEEN 'A' AND 'Z'`) and many had very high spread — combined np ≈ 1,400 park_species pairs that now display in proper Japanese AND are eligible for future profile batches. `Yahazu-endo` alone was np=140 (wider than ソメイヨシノ post-merge).
- Remaining 7 ASCII-prefix species: 2 truly lack a ja name in iNat (Polyphylla laticollis, Streptococcus agalactiae — the latter actually has a ja name starting with 'B'); 1 Sawara homonym; 4 without inat_taxon_id (low np).

### 2026-05-26 (Claude) — A23 + sakura placeholder merge
- A23 batch: +22 profiles (np≥10 remainder + start of np=9). 2,236 → 2,258. 7 common_name_en + 6 zh-Hans aliases backfilled. Cleared the post-cleanup np≥10 sedges + Brassica rapa + Hypericum perforatum.
- New `scripts/merge_species_pair.py`: single-pair version of `merge_duplicate_species`, takes `--from`/`--to` species ids and repoints observations + aliases + photos + profiles; preserves dst common_name_ja; inserts src common_name_ja as a ja alias. Used to merge `サクラ` (NULL-sci, id=181, np=42) into `ソメイヨシノ` (id=252) — combined np now 51, making it the top-spread plant in the demo.
- `ツツジ` (np=25) NOT merged: source pages (akirudai, oizumi-chuo, koganei) explicitly list it alongside サツキ as distinct items, so it's used as a broad genus category and there's no default cultivar to redirect into. Left as NULL-sci.

### 2026-05-26 (Claude) — species_alias partial-unique migration (Active #4 done)
- Dropped `species_alias UNIQUE(raw_name, lang)`; replaced with partial unique index `uniq_alias_resolver` covering only `('ja','ja-kana','sci','en')`. Migration script `scripts/migrate_alias_partial_unique.py` is idempotent; row count preserved (31967→31967). DB backed up to `parklife.db.bak_pre_alias_partial` before run.
- Rationale: `species_alias` was conflating two roles (resolver lookup vs display vernacular). Only resolver langs need uniqueness; display langs (zh-Hans/zh-Hant) are correctly many-to-one per species — `export_html.py:187` uses `setdefault` keyed by species_id, so multiple species sharing a Chinese name causes no display issue.
- Re-ran `scripts.seed_species_profiles` → 27 aliases inserted (the 26 previously collision-blocked + 1 from A22). zh-Hans coverage on profiled species now 98% (51 missing — all genuinely lacking a published Chinese vernacular, no further collisions). `parklife/db.py` schema updated to match. Re-exported docs (34.5 MB) and published to `docs/`.

### 2026-05-26 (Claude) — placeholder-name cleanup + A22 (2231→2236)
- New `scripts/fix_placeholder_names.py`: 9 per-species fixes (hybrid notations cleaned to `マガモ×カルガモ雑種` form; romaji `tsuno-hashibami` → `ツノハシバミ`, `yama-rakkyō` → `ヤマラッキョウ`; genus placeholder `オオハンゴンソウ属` → `アラゲハンゴンソウ`; nakaguro transliterations → canonical katakana). Bulk-stripped 53 redundant `（romaji）` / `（広義）` annotations on Carex etc. Idempotent.
- A22 sidecar batch (+5 profiles) for the originally-noted 5 hybrid/romaji/genus species, all with `common_name_en` + `aliases.{zh-Hans}` fields.

### 2026-05-26 (Claude) — UI chrome i18n: switch full page on language change (commit `a8173a5`)
- Added `CHROME_LABELS` dict (4 langs) covering `<title>`, header label texts, all select option lists, search placeholder, stats template, modal close aria-label, and `<html lang>` attribute.
- New `renderChrome()` JS function called on init + every language change. Header labels marked with `<span class="lbl" data-lbl="…">` so JS can rewrite text without re-rendering full options; select values preserved through option rebuilds.
- Map tile labels NOT switched — OSM default tiles use native script and there's no standard tile-language switch.

### 2026-05-26 (Claude) — profile curation A14–A21: np≥10 tier cleared (2053→2231)
- +178 profiles across 8 batches (commits `d84f817`, `8f16d45`, `a540c28`), sidecar format with `common_name_en` + `aliases.{zh-Hans}`.
- A14 np=12 (bass, Glacial Apollo, Mukashitombo dragonfly, Fire-bellied Newt, European Mantis, Purseweb Spider); A15–A18 np=11→10 (Black Cutworm, Pearly Everlasting, Jimsonweed, Eurasian Curlew, Morel, Forest Cricket); A19–A21 np=10 sweep (Stejneger's Scoter, Fringed Water-lily, Painted-snipe, Eurasian Nuthatch, Wild Boar, Japanese Shrew-mole, Forest Green Tree Frog).
- np≥10 tier exhausted modulo 5 unprofileable placeholders (later cleaned by `fix_placeholder_names`).

### 2026-05-25 (Claude) — profile curation A1–A13 + name sync pipeline (1778→2053)
- +275 profiles across 13 batches A1–A13 (commits `9be2185` → `7ec538a`). Covered np=14–12 tier: national butterfly Sasakia, pomegranate, satsuki, Black-tailed Godwit, Tundra Swan, witch hazel, bigfin reef squid, Macrocilix mysticata bird-dropping mimic, 秋の七草, sedges/mushrooms/inverts, etc.
- Name-sync pipeline (commits `08b8514` → `bbfa587`): closed gap between profiles and species name fields. `common_name_en` NULL 609→18; zh-Hans missing 239→37. Toolchain: regex from profile summaries, iNat `/v1/taxa/{id}?locale=…` (new `scripts/inat_localized_names.py`), Wikidata residual (new `scripts/wikidata_residual_names.py`), manual batches.
- Sidecar format extended (`f124c86`): `species_profiles_extra.json` entries now carry optional `common_name_en` + `aliases.{zh-Hans,zh-Hant}` fields written idempotently by `seed_species_profiles.apply_extra_aliases()`.

### 2026-05-25 (Claude) — P13 URL pass 3 + parking reclassify (1500→1778)
- P13 URL pass 3 (commits `d82c2b2` → `e009cd3`): 124/142 NULL P13 parks filled via 4 parallel research agents + manual JSON; 18 small 緑地/河川敷 confirmed `__no_url__`. Apply script `scripts/apply_manual_park_urls.py`. **Lesson**: instruct agents to Write incremental JSON after EACH park, not at end.
- Parking reclassify (`44b6ce2`, `e009cd3`): new `scripts/fetch_parking_followups.py` + `scripts/reclassify_parking.py`. For each `parking_info LIKE 'OSM:%'` park, refetch official + 4 intra-host links, re-run classify. 91 parks moved OSM-heuristic → text-confirmed; 13 verdict flips on missed lots >300m from centroid.
- +291 profiles across 20 batches: 1487 → 1778 distinct species.

### 2026-05-21 (Claude) — park-specific gallery photos shipped
- New `scripts/park_species_photo.py` + `park_species_photo` table. Per-(park, species) gallery from already-cached iNat + GBIF data (tier-0 ≤600 m, tier-1 ≤5 km) — no new network calls.
- GBIF cache was the unlock: ~80% of GBIF records carry `media[]` array with image + creator + license + lat/lon already park-scoped.
- Full sweep: 122,283 visible pairs → 57,406 (47%) got park-local photos. 46,816 photo rows. Export wiring in `scripts/export_html.py`: per-pair `li` array; `speciesPhotos(sp, pair)` preserves species hero at slot 0 then inserts park-local. Demo 17.1 → 30.3 MB.

### 2026-05-16 (Claude) — TODO #6/3/7/5 batch (P13 expansion + parking + photo + sort)
- P13 expansion (`scripts/p13_seed.py`, commit `e1f93b2`): downloads 国土数値情報 P13 GML zips for 4 pref, filters biodiv park types ≥5 ha, dedupes 500 m radius. +273 parks (209 → 482). Full geo enrichment: iNat +21,792, GBIF +66,406, eBird +4,042 obs.
- OSM parking (`scripts/osm_parking.py`, `6a9ca7d`): Overpass `amenity=parking` within 300 m. Parking NULL 318 → 0.
- Photo gallery rebuild (`scripts/repopulate_species_photos.py` + `wikicommons_hero.py`, `87f5553`): diversity-deduped iNat + Commons P18. 34,979 iNat + 5,822 hero rows. `species_photo.source_url` column added.
- Sort fix (`a85c1ba`): freq sort now `pair.oc` desc primary, `sp.n` tiebreaker (was global-only).

### 2026-05-14/15 (Claude) — Chinese name coverage + sp2000 import (3 sessions)
- Display fallback fixed (`15cbd4c`): zh/zhT users see English with `.name-fallback` dotted-underline, not silently fall back to Japanese.
- `wikidata_zh_broad.py` (P1843 + altLabel SPARQL) + `wikipedia_zh_direct.py` (zh.wiki redirect): +87 aliases.
- `cleanup_zh_aliases.py` removed 48 pinyin aliases; `sp2000_import.py` ingested Catalogue of Life China 2023 DwC-A (288k taxa) → +231 zh-Hans aliases. Visible zh coverage 4,619 → 4,948.

### Older sessions
Pre-2026-05-14 history (initial DB build, prefecture scrapers, Wikipedia normalizer, GBIF/eBird/iNat first passes, modal+photo MVP, repo consolidation to GitHub Pages, Codex collaboration setup) lives in git log. Key infrastructure commits: `9f3add9` (repo init), `e1f93b2` (P13), `87f5553` (photo gallery), `f124c86` (sidecar profile format), `6c9a6b8` (alias partial-unique migration), `bad6563` (romaji fix), `a057858` (dupe-merge pass).
