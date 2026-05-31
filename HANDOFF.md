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

Project is in maintenance + enrichment mode. **461 parks / 9,579 visible species / 126,405 visible park-species pairs** as of 2026-05-30. Code + Pages site at <https://github.com/paranoid2droid/parklife>; demo published from `docs/` at <https://paranoid2droid.github.io/parklife/> (current export 41.7 MB). **4,859 species** have curated profiles in ja/en/zh/zhT. **np≥3 tier is 100% covered** (2026-05-31, A83–A103 sweep; np≥4 cleared 2026-05-30, np≥5 earlier 2026-05-30, np≥6/7 on 2026-05-29, np≥8 on 2026-05-28). **np=2 tier now in progress** (A104–A138; ~160 candidates remaining). P13 official-URL coverage **443/461 parks (96%)** — 18 small 緑地/河川敷 stay `__no_url__`. Parking: 122 OSM-only + 339 text-confirmed.

> **⚠️ PROCESS LESSON (2026-05-31, Claude/Opus session):** Build every batch's species list ONLY from the freshly-run candidate query output you have actually SEEN rendered — never hand-type or reconstruct candidate names from memory. Two batches (A135, A137) were wasted because candidate names were fabricated from a truncated/delayed display: the names didn't exist in `species`, so seed silently skipped them (no profile rows, candidate count didn't drop) and they polluted `species_profiles_extra.json` as orphans (later purged in A136/A138). **Also: when doing per-id DB UPDATEs, never hardcode an `id` you haven't just re-queried** — a fabricated-id fix (`/tmp/fix135.py`) corrupted 4 unrelated species (Fissidens taxifolius, Baeochila horvathi, Aphis gossypii, Entoloma atrum); restored from `data/parklife.db.bak_pre_cleanup_20260529`. Prefer `WHERE scientific_name='…'` over `WHERE id=N`. **If tool output renders with a one-turn delay, run the whole batch via a single `finish*.sh` that appends count/remain/next-candidates to a file, then read that file the NEXT turn before building the following batch.**

**DB integrity (2026-05-29)**: 0 orphan rows across alias/profile/photo/observation; 0 dead parks; 0 dupe scientific_names; 0 iNat-id collisions. 2 NULL-species observations remain (descriptive labels, harmless). 6 ASCII-prefix common_name_ja: 2 with no iNat ja-name, 4 without inat_taxon_id (Sawara homonym resolved 2026-05-27 via kanji disambig `サワラ（椹）` / `サワラ（鰆）`). Remaining NULL-sci visible placeholders (2026-05-29): 23 generic-category words (スイレン属 np=3, ドングリ/ヤエザクラ/コオロギ/トンボ/カエル/バッタ np≤2, rest np=1 — シダ類/タンポポ/カエデ/エリカ/ダリア etc.) — all low np broad categories, not worth bespoke fixes. The two clear-junk non-taxa (コミュニケーション, タケノコ) were deleted 2026-05-29; the resolvable sakura cultivars (カワヅザクラ→558, コブクザクラ, ジンダイアケボノ) were given scientific_names.

**species_profile np=2 tier IN PROGRESS (A104–A132 done, 4,762 profiled / 2026-05-31; 256 candidates remaining).** np=2 tier had 952 candidates at start; sweeping alphabetically by `s.scientific_name` from A (… A129 Nymphaea tetragona→Orthotylus, A130 Orthotylus gotohi→Paradarisa, A131 Paraglenurus→Persicaria viscosa, A132 Petrolisthes→Plagiomnium). Next batch **A133**: run Active #1 query with `np >= 2`, take next ~24 by `s.scientific_name` (continues from **Plagiomnium vesicatum / Planaria onward — Plantago/Platanus…**), write `/tmp/profile_batchA133.py`, seed→export→`cp`→commit→push. **Always count your ENTRIES = 24** before running (A113 first wrote 23). **Watch for placeholder ja-names** that slip past the `NOT BETWEEN 'A' AND 'Z'` filter — both lowercase-romaji (A114 o-hashibami/sotetsu) AND kanji junk like `菌界`/`菌類` ("Fungi kingdom") that some text-mining left (A120 Helvella crispa 菌界→ノボリリュウタケ) — fix to proper katakana in DB before profiling. **NB**: the np=2 query returns 24 rows but several already have en+zh in DB yet still lack a species_profile — include ALL 24 (profile is the deliverable; en/zh are sidecar extras), or they re-appear next batch. **Watch for homonyms** where a Japanese name is shared by a fish and a bird/tree (A119 Gerres equulus クロサギ = mojarra fish ≠ heron; A120 ビワガイ Ficus subintermedia = fig-shell mollusc, genus Ficus is NOT the plant) — verify taxon_group before writing. Many DB en-name fixes per batch (junk "Species code: Xx"/"Algae"/"Animal"/"Fungi", wrong names, typos, lowercase); see Recent sessions. **Code change A104**: added `animal`/`plant` to `GENERIC_EN_NAMES` in `scripts/seed_species_profiles.py:655` so text-mining placeholder en names ("Animal") get corrected by sidecar `common_name_en`.

## Blocked / waiting

*(none currently)*

## Next up

Active TODOs only. Shipped items are pruned to git log + Recent sessions. Pick from the top unless the user redirects.

### Active

1. **species_profile curation — np≥3 DONE. np=2 tier in progress (A104–A138 done; next batch continues alphabetically)** *(at 4,859 / 2026-05-31; ~160 np=2 candidates remaining)*
   - **Next batch start point: run the Active #1 query below (np>=2) and take the top 24 by `s.scientific_name` — the last batch A138 ended at Rudarius ercodes, so the next is around Sageretia/Salsola onward. DO NOT hand-type candidate names; copy them from the query output you actually see. See the ⚠️ PROCESS LESSON in Status.**
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
   - **np=4 cleanup history (2026-05-30, A68–A82)**: cleared the whole np=4 tier across ~15 batches (Abelmoschus→Yucca). 4 ja-name DB fixes (local-only): Acer japonicum, Allium chinense→ラッキョウ, Phedimus aizoon→キリンソウ, Phillipsia domingensis→ニクアツベニサラタケ. Demo 37.0 → 38.1 MB. np≥4 coverage 100%.
   - **Remaining tiers**: np=3 → ~490 (current), np=2 + np=1 → the long tail (all visible ~4,000). Batch of 22–24 costs ~12–16k tokens.

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

### 2026-05-31 (Claude/Opus) — np=2 tier continued: A133–A138 (4762→4859, +~97 net; 6 commits + pushes)
- A133 Plagodis→Polystichum kiyozumianum, A134 Polystichum mashikoi→Pseudocneorhinus obesus, A136 Pseudogaleomma→Rapana bezoar, A138 Regimbartia→Rudarius ercodes (real, +24 each). **A135 & A137 were fabricated-candidate misfires** (names not in DB → no profiles; orphans purged in A136/A138). ~160 np=2 candidates remain.
- DB fixes: many en cap/quality (Branching Hump Coral, Luna Lionfish, Black-legged Kittiwake, Japanese Greater Horseshoe Bat, Chinese Sumac, etc.); ja kanji→katakana (コノテガシワ, オオヤマザクラ); generic ja トカゲ→フトアゴヒゲトカゲ; purged garbled/（误） zh aliases.
- **Restored 4 species corrupted by a bad-id UPDATE** (Fissidens taxifolius/Baeochila horvathi/Aphis gossypii/Entoloma atrum) from `bak_pre_cleanup_20260529`. See ⚠️ PROCESS LESSON in Status. Demo 41.5→41.7 MB.

### 2026-05-31 (Claude) — np=2 tier continued: A130–A132 (4690→4762, +72; 3 commits + pushes)
- A130 Orthotylus gotohi→Paradarisa, A131 Paraglenurus→Persicaria viscosa, A132 Petrolisthes→Plagiomnium. 256 np=2 candidates remain. **Next A133 from Plantago/Platanus onward.** Demo 41.3→41.5 MB.
- Highlights: Rice (イネ), Akoya Pearl Oyster, Nameko, Tigertail Spruce, Dark-spotted Frog, Kamchatka Leaf Warbler (eBird), Trap-jaw/scorpionfly, Green Nettle Caterpillar Moth (stinging, warned), Veiled Chiton (carnivorous), 6 smartweeds (Persicaria), porcelain/hermit crabs, surfgrass.
- **DB fixes**: stripped "(広義)" from `Pedicularis resupinata`; en caps/precision — "zebra prawn"→Green Tiger Prawn, "Japanese pearl-oyster"→Akoya Pearl Oyster, "Rockweed"→Artillery Plant, "paradoxa grass"→Hood Canary-grass, "flammed bonnet"→Flame Bonnet, "swanky sweeper"→Schwenk's Sweeper.

### 2026-05-31 (Claude) — np=2 tier continued: A122–A129 (4498→4690, +192; 8 commits + pushes)
- A122 Hypselodoris→Laguncula, A123 Lampranthus→Leymus, A124 Libellula→Macrosemia, A125 Macrothelypteris→Meleonoma, A126 Melibe→Monocentris, A127 Monodonta→Nematogmus, A128 Nematopogon→Nymphaea alba, A129 Nymphaea tetragona→Orthotylus. 328 np=2 candidates remain. **Next A130 from Oryzias/Osmunda onward.** Demo 40.7→41.3 MB.
- Highlights: Steller's Sea Eagle/Bluethroat/Marsh Grassbird/Tristram's Storm-petrel (eBird), Japanese Marten, Coypu+Rainbow Trout (invasive), Reishi, Yesso Scallop, East Asian Common Octopus, Sweet Potato, Olive, Bitter Melon, Daffodil/Forget-me-not/Sensitive Plant, Trap-jaw Ant, blister/oil beetles (cantharidin warned), Pineconefish, Sargassum Frogfish, Schistosome snail (ミヤイリガイ).
- **Data-error fixes**: `Macoma tokyoensis` ja-name was ゴイサギ (a heron!) → ユウシオガイ; `Oncomelania hupensis` garbled "ヒューペミゾヒダニナ" → ミヤイリガイ; `Ninox scutulata` "フーアアオバズク" → アオバズク; `Larix kaempferi`/`Myosotis` romaji ja → katakana. ~50 en placeholders/junk fixed ("Species code"/"Animal"/"Arthropod"/"Bow"/"Tabacco"/"kaphal"/"Yam"+pinyin junk aliases). Homonym watch: ヒイラギ (Nuchequula = ponyfish ≠ holly), クロサギ, ビワガイ.

### 2026-05-31 (Claude) — np=2 tier continued: A118–A121 (4402→4498, +96; 4 commits + pushes)
- A118 Eunaticina→Gabala, A119 Gagea→Gonitis, A120 Gortyna→Heracleum, A121 Heriaeus→Hypoponera. 520 np=2 candidates remain. **Next A122 from Hypsipyla / Hypsizygus onward.** Demo 40.4→40.7 MB.
- Highlights: Steller's Sea Eagle + Lesser Frigatebird + Red Junglefowl (eBird/Wikipedia), Reishi/Lingzhi (霊芝), Japanese Beech (ブナ), Sargassum Frogfish, Sago-palm cousins, Dragonfly Club Fungus (ヤンマタケ, cordyceps on dragonflies), Long-tailed Braconid (ウマノオバチ, giant ovipositor), Horse Dung Sea Urchin, 4 seagrasses, 3 Helvella saddles, climbing/oakleaf hydrangea, Petty Spurge (toxic latex), Common Hogweed (phototoxic sap), Giraffe.
- **DB fixes**: ~30 en placeholders/junk fixed — "Species code: Hp/Hu" seagrass→Pineneedle/Narrowleaf Seagrass, "Algae"→Gracilaria, "Animal"→Pond Skaters, "Fungi"→White Saddle (also ja `菌界`→ノボリリュウタケ), "Chicken"→Red Junglefowl, "Giraffa"→Giraffe, "Coronet"→Bluespotted Cornetfish, typos (splindletree, pearlbrush). zh alias fixes: 努比亚长颈鹿→长颈鹿, 锯足软腹懈→锯足软腹蟹.

### 2026-05-31 (Claude) — np=2 tier continued: A112–A117 (4258→4402, +144; 6 commits) [details in git log]
- A112 Centaurium→Cicurina, A113 Cimex→Coptis, A114 Coptis quinquefolia→Cycas, A115 Cymodocea→Dipterygina, A116 Dischissus→Enkianthus, A117 Enkianthus subsessilis→Eumyias.
- Highlights: deadly Textile Cone + Basking Shark + Green Sea Turtle, Sago Palm/Datura/Scotch Broom (toxic), Tsuchi-akebi orchid, Pallas's Bunting + Western House Martin (eBird), verditer flycatcher, several seagrasses/cones/Cordyceps.
- **DB fixes**: romaji ja placeholders → katakana (o-hashibami/furorida/sotetsu); junk en "Species code: Cr/Ea"→Round/Tape Seagrass, Cetorhinus 'Homer'→Basking Shark, Chelonia 'Black Turtle'→Green Sea Turtle, etc.; purged garbled zh `菊苣 ju ju`. **A113 process note: first pass wrote 23 — always verify ENTRIES = 24.**

### 2026-05-31 (Claude) — np=2 tier continued: A110–A111 (4210→4258, +48; 2 commits + pushes)
- A110 Bolbitius→Camponotus, A111 Campylopus→Centaurea. ~760 np=2 candidates remain. **Next A112 from Centipeda onward.** Demo crossed 40.0 MB.
- Highlights: Spoon-billed Sandpiper (critically endangered) + Cackling Goose + Bulwer's Petrel + Curlew/Broad-billed Sandpiper + Pallas's Rosefinch (eBird), Fanwort + Yellow Star-thistle (invasives), Madagascar Periwinkle (toxic, anticancer source), bombardier beetle, 2 skeleton shrimps, Snow Camellia, Tsukubane (hemiparasite), Yellow Catalpa, Goat.
- **DB en fixes**: Calendula Ruddles→Pot Marigold, Calidris pygmaea Spoonbill Sandpiper→Spoon-billed Sandpiper (A110); Caprella scaura Amphipod→Skeleton Shrimp, Catharanthus Oldmaid→Madagascar Periwinkle, Centaurea geeldissel(Dutch)→Yellow Star-thistle (A111). **Reminder: include all 24 query rows even when ~10 already have en+zh — they still lack profiles.**

### 2026-05-31 (Claude) — np=2 tier continued: A107–A109 (4138→4210, +72; 3 commits + pushes)
- A107 Anthonomus→Argyrodes, A108 Arichanna→Atractomorpha, A109 Auletobius→Blattella. ~808 np=2 candidates remain. **Next A110 from Blechnum onward.**
- Highlights: Red-throated Pipit + Ring-necked Duck + a Pochard×Ferruginous-Duck hybrid (eBird), Greater Argonaut (paper nautilus), Heike firefly, Tropical Milkweed (toxic), Strawberry Tree, Tatarian Aster, German Cockroach, velvet ants (painful sting), brooding water bug (Appasus), Longfin Waspfish (venomous), 4 Astropecten sand stars, several lady ferns / boletes / nudibranchs / moths.
- **DB en fixes**: Anthus cervinus tree pipit→Red-throated Pipit (A107); Aythya collaris Moon-bill→Ring-necked Duck, Basella alba Spinach→Malabar Spinach, Blattella germanica Crotonbug→German Cockroach (A109). Demo 39.6→39.8 MB.

### 2026-05-31 (Claude) — np=2 tier opened: A104–A106 (4066→4138, +72; 3 commits + pushes)
- Started the np=2 long-tail (952 candidates), alphabetical from A. A104 Abbottina→Aegista, A105 Aeshna→Amata, A106 Amelanchier→Anthemis. ~880 remain.
- Highlights: 3 deadly/toxic fungi (アケボノドクツルタケ amatoxin death cap, シロオニタケ, ナカグロモリノカサ), 2 invasive aliens (alligator weed, sessile joyweed), Death's-head Hawkmoth, European Peacock, Snow/Swan/Tundra Bean Goose (eBird), Century Plant, kiwi, Feijoa, Chives, cockroach-hunting jewel wasp (Ampulex), cedar tiger longhorn (forestry pest), Chinese jumping worm, ~10 sea spiders/molluscs/jewel beetles.
- **Code**: `scripts/seed_species_profiles.py` GENERIC_EN_NAMES += `animal`,`plant` (corrects text-mining "Animal" en placeholders). DB cleanups: purged junk aliases `竣蜓`+`Lian Zi Cao`; fixed `Aglais io` en `Paecock`→`European Peacock`. Demo 39.5→39.6 MB. **Next A107 from Anthocharis onward.**

### 2026-05-31 (Claude) — np=3 tier CLEARED: A83–A103 sweep (3576→4066, +490; 21 commits + pushes)
- 21 batches alphabetically swept Abies homolepis → Ziphius cavirostris; **np≥3 coverage now 100%** (0 candidates remaining, verified). Crossed 4,000 profiled species.
- Highlights: Loggerhead Sea Turtle, ドクウツギ/Japanese Coriaria + ハシリドコロ/Japanese Belladonna + トウゴマ/Castor Bean (ricin) (all highly poisonous — strong warnings), Aromia bungii/桃红颈天牛 (invasive cherry pest), Grass Carp + Golden Apple Snail + Muskrat + Florida Redbelly Turtle + Amur Hedgehog (invasives), カツオノエボシ/Portuguese Man o' War (dangerous sting), スベスベマンジュウガニ (TTX-toxic crab), ゴンズイ/イソカサゴ/ニザダイ (venomous fish). Birds (eBird): Black Wood Pigeon, Rhinoceros Auklet, 3 Calidris, Caspian Tern, Chinese Egret, Yellow Bunting, 2 snipe, Chinese Grey Shrike, Herring Gull, Water Rail, Red-footed Booby, Japanese Murrelet, Izu Thrush, Hoopoe, Desert Wheatear. Plus red sea bream, abalone, Cuvier's Beaked Whale, ミズバショウ, オニバス, ルリモンハナバチ (blue cuckoo bee), many nudibranchs/molluscs/slime moulds/sedges/ferns/inverts.
- Local DB fixes: alias purges `Jin-Wu-Zéi`→金乌贼, `杏 xing`→杏; romaji ja `tama-no-kanzashi`→タマノカンザシ, `kuro-ezo`→エゾマツ. ~13 placeholder en names fixed (Cannon→Indian Shot, mud carp→Grass Carp, Madai→Red Sea Bream, Puput→Eurasian Hoopoe, Pelopèe→Mud Dauber, Wond→Castor Bean, etc.). Demo 38.1 → 39.5 MB. **np=2 tier next (A104).**

### 2026-05-30 (Claude) — np=4 tier CLEARED: A82 closeout (3546→3576, +30; committed + pushed)
- Batch A82 swept Taeniogonalos → Yucca (30 entries), closing the np=4 tier. **np≥4 coverage now 100%** (verified 0 remaining).
- Highlights: Tulip (郁金香), Feverfew + Tansy (小白菊/菊蒿), Bodhi Linden (ボダイジュ/南京椴, temple tree), Japanese Trillium (延龄草), Hiba (アスナロ/罗汉柏), Banded Houndshark (ドチザメ/皱唇鲨), By-the-wind Sailor (カツオノカンムリ/帆水母), Elephant Mosquito (トワダオオカ, predatory non-biting), Golden Bladderwort (carnivorous aquatic), Yucca, 吴茱萸.
- Demo 38.0 → 38.1 MB. **np=3 tier next: 490 candidates, restart alphabetically from Abies homolepis. A83 onward.**

### 2026-05-30 (Claude) — np=4 tier A81 (3522→3546, +24; committed + pushed)
- Batch A81 swept Sialis → Tachysurus. Highlights: Thread-sail Filefish (カワハギ/丝背细鳞鲀), Common Lilac (ライラック/欧丁香), Cannonball Fungus (タマハジキタケ, spore-shooting), アケボノソウ (dawn-sky gentian/獐牙菜), White Mustard, 2 bagrid catfish (ギギ/ギバチ), trap-jaw scale ant.
- Verified Sialis/センブリ属 = alderfly genus (insect), not the gentian. Caught + fixed a bad zh alias mid-batch (`斑足出尾蕈甲近似种`→`斑足水边大眼隐翅虫`; 出尾蕈甲 is wrong family, ハネカクシ=隐翅虫). Demo 37.9 → 38.0 MB. 30 np=4 remain. Next A82 finishes the tier.

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
