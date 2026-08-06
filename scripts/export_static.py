"""Export the read-only API as static JSON shards for zero-server hosting.

This is the productization P2 step: instead of running ``scripts/serve_api``
(a Python process) or shipping the whole ``parklife-data.json`` (71 MB) to the
browser, we pre-bake the API's access pattern into static files that any dumb
static host (GitHub Pages, Cloudflare Pages, S3, ...) can serve. The thin-client
``webapp/app.js`` fetches these on demand exactly as it used to fetch ``/api/*``.

Layout (written under ``site/`` — the deployable artifact, gitignored):

    site/
      index.html app.js sw.js manifest.webmanifest icon*        (copied shell)
      .nojekyll                                                  (GitHub Pages)
      data/
        parks.json                     light park index (all parks, coords)
        parks/<id>.json                one park + its species summary cards
        park-photos/<id>.json          {species_id: [[url,attr,src,source]]}
        species/<bucket>.json          {species_id: full detail}   (BUCKETS files)
        species-parks/<bucket>.json    {species_id: [park_id, ...]} (BUCKETS files)
        search-index.json              [[id,sci,ja,en,zh,zhT,group,photo,np], ...]
        meta.json                      {buckets, parks, species, generated}

Species detail and species->parks are *bucketed* by ``id % BUCKETS`` to keep the
file count well under static-host limits (Cloudflare Pages caps a project at
20k files) while still lazy-loading only a slice per interaction.

Run:
    .venv/bin/python -m scripts.export_static

The shapes deliberately reuse ``parklife.api`` so the client can consume either
this static export or a live ``serve_api`` unchanged.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path

from parklife import api

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site"
WEBAPP = ROOT / "webapp"

# MUST match SPECIES_BUCKETS in webapp/app.js.
BUCKETS = 512

# The thin-client shell copied verbatim next to the data/ dir.
STATIC_ASSETS = [
    "index.html", "app.js", "sw.js", "manifest.webmanifest",
    "icon.svg", "icon-192.png", "icon-512.png",
]


def bucket_of(i: int) -> int:
    return ((i % BUCKETS) + BUCKETS) % BUCKETS


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # minified (compact separators); ensure_ascii=False keeps JP/CN as UTF-8
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def main() -> None:
    t0 = time.time()

    # One shared read-only connection for the whole run. api.* opens a fresh
    # connection per call otherwise; monkeypatching _connect to a single RO
    # handle turns ~28k reconnects into zero. mode=ro (not immutable) still
    # respects any -wal, so we never read stale pages.
    shared = sqlite3.connect(f"file:{api.DB_PATH}?mode=ro", uri=True)
    shared.row_factory = sqlite3.Row
    api._connect = lambda: shared  # type: ignore[assignment]

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / ".nojekyll").write_text("")  # tell GitHub Pages not to run Jekyll

    for a in STATIC_ASSETS:
        shutil.copy(WEBAPP / a, OUT / a)

    data = OUT / "data"
    data.mkdir()

    # 1. park index (all parks; the client filters to those with coords) --------
    parks = api.park_index()
    write_json(data / "parks.json", parks)
    print(f"parks.json: {len(parks)} parks")

    # 2. per-park detail (species summary cards) -------------------------------
    (data / "parks").mkdir()
    for p in parks:
        write_json(data / "parks" / f'{p["id"]}.json', api.park_detail(p["id"]))
    print(f"parks/*.json: {len(parks)} files")

    # 3. park-local pair photos, grouped per park ------------------------------
    (data / "park-photos").mkdir()
    pp: dict[int, dict[int, list]] = {}
    for r in shared.execute(
        "SELECT park_id, species_id, url, attribution, source_url, source "
        "FROM park_species_photo ORDER BY park_id, species_id, sort_order, id"
    ):
        pp.setdefault(r["park_id"], {}).setdefault(r["species_id"], []).append(
            [api.medium_photo_url(r["url"]), r["attribution"], r["source_url"], r["source"]])
    for pid, m in pp.items():
        write_json(data / "park-photos" / f"{pid}.json", m)
    print(f"park-photos/*.json: {len(pp)} files")

    # 4. reachable species (everything a park card / search result can open) ----
    reachable = [r[0] for r in shared.execute(
        "SELECT DISTINCT species_id FROM park_species ORDER BY species_id")]

    # 5. species detail buckets -------------------------------------------------
    (data / "species").mkdir()
    sb: dict[int, dict[int, dict]] = {}
    for n, sid in enumerate(reachable, 1):
        d = api.species_detail(sid)
        if d:
            sb.setdefault(bucket_of(sid), {})[sid] = d
        if n % 5000 == 0:
            print(f"  species detail {n}/{len(reachable)}")
    for b in range(BUCKETS):
        write_json(data / "species" / f"{b}.json", sb.get(b, {}))
    print(f"species/*.json: {BUCKETS} buckets, {len(reachable)} species")

    # 6. species -> park-id list buckets (reverse map view needs ids only) -----
    (data / "species-parks").mkdir()
    spb: dict[int, dict[int, list[int]]] = {}
    for r in shared.execute(
        "SELECT species_id, park_id FROM park_species "
        "ORDER BY species_id, observation_count DESC"
    ):
        spb.setdefault(bucket_of(r["species_id"]), {}).setdefault(
            r["species_id"], []).append(r["park_id"])
    for b in range(BUCKETS):
        write_json(data / "species-parks" / f"{b}.json", spb.get(b, {}))
    print(f"species-parks/*.json: {BUCKETS} buckets")

    # 7. search index ----------------------------------------------------------
    # zh/zh-Hant aliases in one pass (avoid a 24k-param IN clause).
    zmap: dict[int, tuple] = {}
    for r in shared.execute(
        "SELECT species_id, lang, raw_name FROM species_alias "
        "WHERE lang IN ('zh-Hans','zh-Hant')"
    ):
        zh, zht = zmap.get(r["species_id"], (None, None))
        if r["lang"] == "zh-Hans" and not zh:
            zh = r["raw_name"]
        elif r["lang"] == "zh-Hant" and not zht:
            zht = r["raw_name"]
        zmap[r["species_id"]] = (zh, zht)
    npmap = {r[0]: r[1] for r in shared.execute(
        "SELECT species_id, COUNT(*) FROM park_species GROUP BY species_id")}
    rs = set(reachable)
    idx = []
    for r in shared.execute(
        "SELECT id, scientific_name, common_name_ja, common_name_en, "
        "taxon_group, kingdom, photo_url FROM species"
    ):
        if r["id"] not in rs:
            continue
        zh, zht = zmap.get(r["id"], (None, None))
        idx.append([
            r["id"], r["scientific_name"], r["common_name_ja"], r["common_name_en"],
            zh, zht, api.demo_group(r["taxon_group"], r["kingdom"]),
            api.medium_photo_url(r["photo_url"]), npmap.get(r["id"], 1),
        ])
    write_json(data / "search-index.json", idx)
    print(f"search-index.json: {len(idx)} species")

    # 8. season shards: visible species in season per month --------------------
    # `park_species.months_bitmap` (bit m = month m+1, OR'd across sources) is
    # the per-(park,species) phenology. For a global "what's in season this
    # month" browse we rank species by how many parks record them in that month
    # (tiebreak: overall spread). NULL/0 bitmaps = year-round/unknown, excluded.
    # Payload is [[species_id, in_season_park_count], ...]; the client joins to
    # search-index for names/photos, so no data is duplicated across months.
    (data / "season").mkdir()
    vis_ids = {r[0] for r in shared.execute(
        "SELECT id FROM species WHERE common_name_ja IS NOT NULL AND common_name_ja!=''")}
    month_counts: list[dict[int, int]] = [{} for _ in range(12)]
    for r in shared.execute(
        "SELECT species_id, months_bitmap FROM park_species "
        "WHERE months_bitmap IS NOT NULL AND months_bitmap!=0"
    ):
        sid, mb = r["species_id"], r["months_bitmap"]
        if sid not in vis_ids or sid not in rs:
            continue
        for m in range(12):
            if mb & (1 << m):
                month_counts[m][sid] = month_counts[m].get(sid, 0) + 1
    season_counts = []
    for m in range(12):
        ranked = sorted(month_counts[m].items(),
                        key=lambda kv: (-kv[1], -npmap.get(kv[0], 1)))
        write_json(data / "season" / f"{m + 1}.json", ranked)
        season_counts.append(len(ranked))
    print(f"season/*.json: 12 months, in-season counts {season_counts}")

    # 9. meta ------------------------------------------------------------------
    write_json(data / "meta.json", {
        "buckets": BUCKETS, "parks": len(parks),
        "species": len(reachable), "generated": int(time.time()),
        "seasonCounts": season_counts,
    })

    print(f"done in {time.time() - t0:.1f}s -> {OUT}")


if __name__ == "__main__":
    main()
