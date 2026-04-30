# parklife

A database of flora and fauna observed in Japanese parks, scraped from official park websites.

Initial scope: parks managed by Tokyo (都立), Kanagawa (県立), Chiba (県立), and Saitama (県立).

## Layout

```
data/
  seeds/        — curated lists of parks per prefecture (YAML)
  raw/          — cached HTML per source URL (gitignored)
  parklife.db   — SQLite output
parklife/
  db.py         — schema + helpers
  seeds.py      — load seed lists
  scrapers/     — per-park-system scrapers
  normalize/    — species name normalization (ja ↔ scientific)
scripts/        — CLI entry points
```

## Setup

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Running

```bash
.venv/bin/python -m scripts.init_db          # create empty parklife.db
.venv/bin/python -m scripts.scrape <prefecture>  # scrape one prefecture
```
