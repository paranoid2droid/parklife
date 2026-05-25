# species_profile batch template

Copy `/tmp/profile_batchN.py` template below, fill in 20-25 species, and run.

## Quick start checklist

```bash
# 1. Find next candidates (skip romaji-only ja names via SUBSTR check)
sqlite3 -header -column data/parklife.db "
SELECT s.scientific_name, s.common_name_ja, s.taxon_group,
       COUNT(DISTINCT ps.park_id) AS np
FROM species s
JOIN park_species ps ON ps.species_id=s.id
LEFT JOIN species_profile sp ON sp.species_id=s.id
WHERE sp.species_id IS NULL
  AND s.scientific_name IS NOT NULL
  AND s.common_name_ja IS NOT NULL
  AND s.common_name_ja <> ''
  AND SUBSTR(s.common_name_ja,1,1) NOT BETWEEN 'A' AND 'Z'
GROUP BY s.id
ORDER BY np DESC, s.scientific_name
LIMIT 30;
"

# 2. Write batch (see template below), then:
.venv/bin/python /tmp/profile_batchN.py \
  && .venv/bin/python -m scripts.seed_species_profiles 2>&1 | grep -E "(upserted|backfilled)" \
  && .venv/bin/python -m scripts.export_html 2>&1 | tail -1 \
  && cp data/export/index.html docs/index.html

# 3. Verify count, commit, push
sqlite3 data/parklife.db "SELECT COUNT(DISTINCT species_id) FROM species_profile;"
git add data/species_profiles_extra.json docs/index.html
git commit -m "species profiles: +N (batch X, tier desc)" -m "Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

## Batch script skeleton

Save as `/tmp/profile_batchN.py` (replace N with your batch letter, e.g. A6):

```python
"""Batch A6 — np=14 remainder + np=13 (or whatever the current tier is)."""

import json
from pathlib import Path

JSON_FP = Path('/Users/zhe/ClaudeCode/parklife/data/species_profiles_extra.json')
data = json.loads(JSON_FP.read_text(encoding='utf-8'))

ENTRIES = {
  "Genus species": {
    "sources": ["iNaturalist", "Wikipedia"],          # also add "eBird" for birds
    "common_name_en": "Plain English Name",            # omit if iNat already has one
    "aliases": {"zh-Hans": "中文俗名"},                # omit if DB already has zh-Hans
    "ja": {
      "summary": "和名。本州〜九州の…分布する…科の…。…",
      "habitat_hint": "雑木林、…、…。…を好む。",
      "finding_tips": "X〜Y月、…で…を探します。…が識別ポイント。"
    },
    "en": {
      "summary": "English Common Name. A … of … from Honshu to Kyushu. …",
      "habitat_hint": "…, …, … — …",
      "finding_tips": "From X to Y look at … for … . The … is diagnostic."
    },
    "zh": {
      "summary": "中文名（和名）。本州至九州…分布之…科。…",
      "habitat_hint": "…、…、…。喜…。",
      "finding_tips": "X 至 Y 月，于…寻找…。…为辨识要点。"
    }
  },
  # ... 19 more entries ...
}


added, skipped = 0, []
for k, v in ENTRIES.items():
    if k in data:
        skipped.append(k); continue
    data[k] = v
    added += 1

if skipped: print(f"SKIP existing: {skipped}")
JSON_FP.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f"added {added} new profiles, total now {len(data)}")
```

## Field guidelines

- **`common_name_en`**: only set when DB `common_name_en` is NULL or generic ("Moth"/"Butterfly"/"Beetle"/"Fly"/"Bug"). Check with `sqlite3 data/parklife.db "SELECT common_name_en FROM species WHERE scientific_name='X';"` before adding.
- **`aliases.zh-Hans`**: only set when DB `species_alias WHERE lang='zh-Hans'` is missing. `aliases.zh-Hant` rarely needed (zhT display auto-derived from zh via OpenCC at export time).
- **Profile summaries**: lead with the common name in that language, then characterize the species in 1-3 sentences. Mention toxicity/danger explicitly if relevant (snakes, hornets, poisonous plants/mushrooms).
- **`habitat_hint`**: short phrase, comma-separated environment list.
- **`finding_tips`**: month range + where to look + diagnostic feature.
- **`sources`**: always at least `["iNaturalist", "Wikipedia"]`. Add `"eBird"` for birds. Used by `seed_species_profiles.py` to generate clickable reference links in the modal.

## Skip rules

- `common_name_ja` is NULL or empty → not visible in demo, skip.
- `common_name_ja` starts with ASCII letter (e.g. `Yabu-tsuru-azuki`, `Oo-kuro-kogane`) → iNat romaji placeholder, skip.
- `common_name_ja` is just `（…）` parens content with no katakana → likely placeholder, skip.

## Tone

- ja: 自然な日本語、現代の動植物図鑑風。専門用語OK。
- en: clear field-guide style; avoid jargon unless taxonomically necessary.
- zh: 简体中文，自然书面语。可借鉴《中国植物志》/《中国动物志》风格用语。

## Pace

- 20–25 entries per batch
- Run pipeline + commit per 1–2 batches
- Each batch is ~8-10k tokens of script content
- Plan for ~13 batches to clear np≥10 from current 1,878 → ~2,150
