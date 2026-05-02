"""SQLite schema and helpers for the parklife database.

Design notes:
- `species` is the canonical taxon record; multiple raw names from different
  parks resolve to the same species via `species_alias`.
- `observation` is the flexible bridge between (park, species) — a single park
  may list a species with seasonal info, location-within-park, and free-form
  notes. Unresolved raw names go into `observation` with species_id = NULL
  and are queued for manual review via `species_alias.status = 'pending'`.
- `source` records every fetched URL so re-scrapes are idempotent and we can
  trace any datum back to the page it came from.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS park (
    id              INTEGER PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    name_ja         TEXT NOT NULL,
    name_en         TEXT,
    prefecture      TEXT NOT NULL,           -- 'tokyo' | 'kanagawa' | 'chiba' | 'saitama'
    municipality    TEXT,
    operator        TEXT,                    -- managing body, e.g. '東京都公園協会'
    official_url    TEXT,
    lat             REAL,
    lon             REAL,
    area_m2         INTEGER,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS species (
    id              INTEGER PRIMARY KEY,
    scientific_name TEXT UNIQUE,             -- Latin binomial, may be NULL when unknown
    common_name_ja  TEXT,
    common_name_en  TEXT,
    kingdom         TEXT,                    -- 'animalia' | 'plantae' | 'fungi' | 'other'
    taxon_group     TEXT,                    -- 'bird' | 'insect' | 'mammal' | 'reptile' |
                                             -- 'amphibian' | 'fish' | 'tree' | 'shrub' |
                                             -- 'herb' | 'fern' | 'moss' | 'mushroom' | 'other'
    rank            TEXT DEFAULT 'species',  -- 'species' | 'genus' | 'family' | ...
    inat_taxon_id   INTEGER,                 -- iNaturalist taxon id (for follow-up queries)
    photo_url       TEXT                     -- representative photo (medium size) from iNat
);

CREATE TABLE IF NOT EXISTS species_alias (
    id              INTEGER PRIMARY KEY,
    species_id      INTEGER REFERENCES species(id) ON DELETE CASCADE,
    raw_name        TEXT NOT NULL,           -- name as it appeared on the source page
    lang            TEXT,                    -- 'ja' | 'ja-kana' | 'en' | 'sci'
    status          TEXT NOT NULL DEFAULT 'resolved',
                                             -- 'resolved' | 'pending' | 'rejected'
    UNIQUE(raw_name, lang)
);

CREATE TABLE IF NOT EXISTS source (
    id              INTEGER PRIMARY KEY,
    park_id         INTEGER REFERENCES park(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,           -- ISO 8601 UTC
    http_status     INTEGER,
    content_sha256  TEXT,
    raw_path        TEXT,                    -- relative path under data/raw/
    UNIQUE(url, fetched_at)
);

CREATE TABLE IF NOT EXISTS observation (
    id              INTEGER PRIMARY KEY,
    park_id         INTEGER NOT NULL REFERENCES park(id) ON DELETE CASCADE,
    species_id      INTEGER REFERENCES species(id) ON DELETE SET NULL,
    raw_name        TEXT NOT NULL,           -- preserve what the page actually said
    months_bitmap   INTEGER,                 -- bit 0 = Jan, bit 11 = Dec; NULL = year-round/unknown
    location_hint   TEXT,                    -- e.g. '池の周辺', '雑木林'
    characteristics TEXT,                    -- free-form notes from the page
    source_id       INTEGER REFERENCES source(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_observation_park    ON observation(park_id);
CREATE INDEX IF NOT EXISTS idx_observation_species ON observation(species_id);
CREATE INDEX IF NOT EXISTS idx_alias_raw_name      ON species_alias(raw_name);

-- Derived from `observation`: one row per (park, species) with months OR'd
-- across all sources. Rebuild via scripts.dedupe whenever observation changes.
-- Treat as read-only — do not mutate directly.
CREATE TABLE IF NOT EXISTS park_species (
    park_id           INTEGER NOT NULL REFERENCES park(id) ON DELETE CASCADE,
    species_id        INTEGER NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    months_bitmap     INTEGER,
    observation_count INTEGER NOT NULL,
    source_count      INTEGER NOT NULL,
    raw_names         TEXT,    -- pipe-separated unique raw names seen for this pair
    location_hints    TEXT,    -- semicolon-joined unique location hints
    characteristics   TEXT,    -- semicolon-joined unique characteristics notes
    PRIMARY KEY (park_id, species_id)
);

CREATE INDEX IF NOT EXISTS idx_park_species_park    ON park_species(park_id);
CREATE INDEX IF NOT EXISTS idx_park_species_species ON park_species(species_id);
CREATE INDEX IF NOT EXISTS idx_park_species_months  ON park_species(months_bitmap);

-- Optional photo gallery for species detail modals. Populated by
-- scripts.collect_species_photos from licensed iNaturalist observation photos.
CREATE TABLE IF NOT EXISTS species_photo (
    id              INTEGER PRIMARY KEY,
    species_id      INTEGER NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    thumb_url       TEXT,
    attribution     TEXT,
    source          TEXT NOT NULL DEFAULT 'iNaturalist',
    sort_order      INTEGER NOT NULL DEFAULT 0,
    UNIQUE(species_id, url)
);

CREATE INDEX IF NOT EXISTS idx_species_photo_species ON species_photo(species_id);

-- Optional species-level field guide text for the detail modal. The demo uses
-- this when available and falls back to group-level guide text otherwise.
CREATE TABLE IF NOT EXISTS species_profile (
    id              INTEGER PRIMARY KEY,
    species_id      INTEGER NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    lang            TEXT NOT NULL,           -- 'ja' | 'en' | 'zh' | 'zhT'
    summary         TEXT NOT NULL,
    habitat_hint    TEXT,
    finding_tips    TEXT,
    sources         TEXT,                    -- JSON array or short source note
    source_urls     TEXT,                    -- JSON array of {label,url}
    updated_at      TEXT NOT NULL,
    UNIQUE(species_id, lang)
);

CREATE INDEX IF NOT EXISTS idx_species_profile_species_lang ON species_profile(species_id, lang);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.row_factory = sqlite3.Row
    return conn


def init(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
