"""Reclaim disk by slimming/pruning regeneratable caches.

The heavy caches under data/cache/ store *entire* upstream API responses even
though the downstream photo-selection scripts read only a handful of fields per
record. This tool shrinks them in place (keeping them re-runnable) and trims old
DB backups. Everything it touches is either regeneratable or a point-in-time
snapshot; the authoritative URLs are already baked into the species_photo /
park_species_photo tables.

Usage:
    python -m scripts.prune_caches report                 # show sizes only
    python -m scripts.prune_caches slim-inat [--dry-run]  # shrink inat photo caches in place
    python -m scripts.prune_caches trim-backups --keep 1  # delete all but newest N DB backups

`slim-inat` keeps only the fields park_species_photo.py / collect_species_photos.py
actually read (see PHOTO_KEYS / OBS_KEYS), typically a ~25-30x reduction.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INAT_CACHES = [
    ROOT / "data" / "cache" / "inat_photos",
    ROOT / "data" / "cache" / "inat_photos_broad",
]

# Fields the downstream readers touch. Everything else in an iNat observation
# response (annotations, identifications, quality_metrics, comments, tags,
# moderator_actions, flags, project_ids, ...) is dead weight.
PHOTO_KEYS = (
    "id", "url", "square_url", "medium_url",
    "license_code", "attribution", "original_dimensions",
)
OBS_KEYS_SCALAR = ("id", "observed_on")


def _slim_obs(obs: dict) -> dict:
    out = {k: obs.get(k) for k in OBS_KEYS_SCALAR}
    ood = obs.get("observed_on_details") or {}
    out["observed_on_details"] = {"date": ood.get("date")}
    out["geojson"] = obs.get("geojson")
    out["user"] = {"login": (obs.get("user") or {}).get("login")}
    out["photos"] = [
        {k: ph.get(k) for k in PHOTO_KEYS if ph.get(k) is not None}
        for ph in (obs.get("photos") or [])
    ]
    return out


def slim_payload(data: dict) -> dict:
    """Reduce a full /observations response to just the photo-selection fields."""
    return {
        "total_results": data.get("total_results"),
        "per_page": data.get("per_page"),
        "page": data.get("page"),
        "results": [_slim_obs(o) for o in (data.get("results") or [])],
    }


# --- GBIF occurrence cache (data/cache/gbif/<pref>__<slug>.json = list of records) ---
# Union of fields read by the three consumers of this cache:
#   scripts/gbif.py (ingestion), scripts/repair_animal_groups.py,
#   scripts/park_species_photo.py (photo selection).
GBIF_OCC_KEYS = (
    "speciesKey", "taxonKey", "key",
    "species", "scientificName", "vernacularName",
    "kingdom", "phylum", "class", "order", "family",
    "decimalLatitude", "decimalLongitude", "recordedBy", "eventDate",
    "individualCount",   # GBIF survey counts (モニタリングサイト1000 etc.) = true abundance
)
GBIF_MEDIA_KEYS = (
    "identifier", "references", "type", "format",
    "creator", "license", "rightsHolder", "title",
)
GBIF_CACHE = ROOT / "data" / "cache" / "gbif"


def _slim_gbif_rec(rec: dict) -> dict:
    out = {k: rec.get(k) for k in GBIF_OCC_KEYS if rec.get(k) is not None}
    media = rec.get("media")
    if media:
        out["media"] = [
            {k: m.get(k) for k in GBIF_MEDIA_KEYS if m.get(k) is not None}
            for m in media
        ]
    return out


def slim_gbif(records: list) -> list:
    """Reduce a GBIF occurrence list to the ingestion + photo-selection fields."""
    return [_slim_gbif_rec(r) for r in records if isinstance(r, dict)]


def cmd_slim_gbif(dry_run: bool) -> None:
    if not GBIF_CACHE.exists():
        print("no gbif cache")
        return
    files = sorted(GBIF_CACHE.glob("*.json"))
    before = _dirsize(GBIF_CACHE)
    print(f"gbif: {len(files)} files, {_human(before)}")
    saved = 0
    for i, fp in enumerate(files, 1):
        try:
            raw = fp.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:
            print(f"  skip {fp.name}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, list):
            continue
        new = json.dumps(slim_gbif(data), ensure_ascii=False)
        if len(new) >= len(raw):
            continue
        saved += len(raw) - len(new)
        if not dry_run:
            fp.write_text(new, encoding="utf-8")
        if i % 2000 == 0:
            print(f"  ...{i}/{len(files)}")
    print(f"gbif: {_human(before)} -> ~{_human(before - saved)} "
          f"({'would reclaim' if dry_run else 'reclaimed'} ~{_human(saved)})")


def _dirsize(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}"
        n /= 1024


def cmd_slim_inat(dry_run: bool) -> None:
    before_total = after_total = 0
    for cache in INAT_CACHES:
        if not cache.exists():
            continue
        files = sorted(cache.glob("*.json"))
        cb = _dirsize(cache)
        before_total += cb
        print(f"{cache.name}: {len(files)} files, {_human(cb)}")
        saved_bytes = 0
        for i, fp in enumerate(files, 1):
            try:
                raw = fp.read_text(encoding="utf-8")
                data = json.loads(raw)
            except Exception as e:
                print(f"  skip {fp.name}: {e}", file=sys.stderr)
                continue
            # Already slim? detect by presence of a heavy key on first obs.
            slim = slim_payload(data)
            new = json.dumps(slim, ensure_ascii=False)
            if len(new) >= len(raw):
                continue  # nothing to gain (already slim or empty)
            saved_bytes += len(raw) - len(new)
            if not dry_run:
                fp.write_text(new, encoding="utf-8")
            if i % 2000 == 0:
                print(f"  ...{i}/{len(files)}")
        after = cb - saved_bytes
        after_total += after
        print(f"  -> ~{_human(after)} ({'would save' if dry_run else 'saved'} ~{_human(saved_bytes)})")
    print(f"TOTAL: {_human(before_total)} -> ~{_human(after_total)} "
          f"({'would reclaim' if dry_run else 'reclaimed'} ~{_human(before_total - after_total)})")


def cmd_trim_backups(keep: int) -> None:
    baks = sorted((ROOT / "data").glob("parklife.db.bak_*"))
    if len(baks) <= keep:
        print(f"{len(baks)} backups, keep={keep}: nothing to delete")
        return
    to_delete = baks[:-keep] if keep > 0 else baks
    freed = 0
    for b in to_delete:
        sz = b.stat().st_size
        freed += sz
        print(f"delete {b.name} ({_human(sz)})")
        b.unlink()
    kept = baks[-keep:] if keep > 0 else []
    for b in kept:
        print(f"keep   {b.name}")
    print(f"reclaimed ~{_human(freed)}")


def cmd_report() -> None:
    cache = ROOT / "data" / "cache"
    rows = []
    if cache.exists():
        for d in sorted(cache.iterdir()):
            if d.is_dir():
                rows.append((d.name, _dirsize(d)))
    rows.sort(key=lambda r: -r[1])
    print("== data/cache ==")
    for name, sz in rows[:15]:
        print(f"  {_human(sz):>10}  {name}")
    baks = sorted((ROOT / "data").glob("parklife.db.bak_*"))
    btotal = sum(b.stat().st_size for b in baks)
    print(f"== DB backups: {len(baks)} files, {_human(btotal)} ==")


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "report"
    dry = "--dry-run" in argv
    if cmd == "report":
        cmd_report()
    elif cmd == "slim-inat":
        cmd_slim_inat(dry)
    elif cmd == "slim-gbif":
        cmd_slim_gbif(dry)
    elif cmd == "trim-backups":
        keep = 1
        if "--keep" in argv:
            keep = int(argv[argv.index("--keep") + 1])
        cmd_trim_backups(keep)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
