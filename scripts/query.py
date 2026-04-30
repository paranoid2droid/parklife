"""Query CLI for the parklife database.

Subcommands:
  stats              overall counts
  bloom <month>      species likely to be in season in month N (1-12),
                     grouped by park
  where <name>       parks where a species (raw or canonical name) is listed
  park <slug>        full info for one park
  species [--group]  list resolved species, optionally filter by taxon_group
  prefecture <code>  summary by prefecture (tokyo|kanagawa|chiba|saitama)
  search <substr>    search species by Japanese or scientific name substring

All queries are read-only; no mutations.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"

MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def cmd_stats(args) -> None:
    c = conn()
    row = lambda q, *a: c.execute(q, a).fetchone()[0]
    print(f"Parks         : {row('SELECT COUNT(*) FROM park')}")
    print(f"  with data   : {row('SELECT COUNT(DISTINCT park_id) FROM park_species')}")
    print(f"Species       : {row('SELECT COUNT(*) FROM species')}")
    print(f"  with sci    : {row('SELECT COUNT(*) FROM species WHERE scientific_name IS NOT NULL')}")
    print(f"Aliases       : {row('SELECT COUNT(*) FROM species_alias')}")
    print(f"Observations  : {row('SELECT COUNT(*) FROM observation')}")
    print(f"  linked      : {row('SELECT COUNT(*) FROM observation WHERE species_id IS NOT NULL')}")
    print(f"  deduped pairs: {row('SELECT COUNT(*) FROM park_species')}")
    print(f"\nBy prefecture (deduped park-species pairs):")
    for r in c.execute("""
        SELECT park.prefecture,
               COUNT(ps.species_id) AS pairs,
               COUNT(DISTINCT park.id) AS parks_total,
               COUNT(DISTINCT ps.park_id) AS parks_with_obs
        FROM park LEFT JOIN park_species ps ON ps.park_id=park.id
        GROUP BY park.prefecture ORDER BY pairs DESC
    """):
        print(f"  {r['prefecture']:<10} {r['pairs']:>5} pairs  "
              f"({r['parks_with_obs']}/{r['parks_total']} parks)")
    print(f"\nBy taxon_group (unique species + deduped pairs):")
    for r in c.execute("""
        SELECT COALESCE(species.taxon_group,'?') AS g,
               COUNT(DISTINCT species.id) AS sp,
               COUNT(*) AS pairs
        FROM park_species ps JOIN species ON species.id=ps.species_id
        GROUP BY g ORDER BY pairs DESC
    """):
        print(f"  {r['g']:<10} {r['sp']:>4} species  {r['pairs']:>5} pairs")


def cmd_bloom(args) -> None:
    month = int(args.month)
    if not 1 <= month <= 12:
        sys.exit("month must be 1..12")
    bit = 1 << (month - 1)
    c = conn()
    print(f"=== {MONTH_NAMES[month]} ({month}月) — species in season, by park ===\n")
    rows = list(c.execute("""
        SELECT park.name_ja, park.prefecture,
               species.common_name_ja AS sp_ja,
               species.scientific_name AS sp_sci,
               species.taxon_group AS grp
        FROM park_species ps
        JOIN park    ON park.id=ps.park_id
        JOIN species ON species.id=ps.species_id
        WHERE (ps.months_bitmap & ?) > 0
        ORDER BY park.prefecture, park.name_ja, species.common_name_ja
    """, (bit,)))
    if not rows:
        print("(none)")
        return
    last_park = None
    for r in rows:
        park = f"{r['name_ja']} [{r['prefecture']}]"
        if park != last_park:
            print(f"\n  {park}")
            last_park = park
        sci = f"  ({r['sp_sci']})" if r['sp_sci'] else ""
        grp = f"[{r['grp']}]" if r['grp'] else ""
        print(f"    - {r['sp_ja']:<20} {grp:<10}{sci}")
    print(f"\n  total rows: {len(rows)}")


def cmd_where(args) -> None:
    name = args.name
    c = conn()
    # Resolve the species via species_alias (covers ja / sci / en variants)
    sp = c.execute("""
        SELECT s.id, s.common_name_ja, s.scientific_name FROM species s
        WHERE s.common_name_ja=? OR s.scientific_name=?
        UNION
        SELECT s.id, s.common_name_ja, s.scientific_name
        FROM species s JOIN species_alias a ON a.species_id=s.id
        WHERE a.raw_name=?
        LIMIT 1
    """, (name, name, name)).fetchone()
    if sp:
        rows = list(c.execute("""
            SELECT park.slug, park.name_ja, park.prefecture, park.municipality,
                   ps.raw_names, ps.months_bitmap, ps.characteristics, ps.source_count
            FROM park_species ps
            JOIN park ON park.id=ps.park_id
            WHERE ps.species_id=?
            ORDER BY park.prefecture, park.name_ja
        """, (sp["id"],)))
    else:
        rows = []
    if not rows:
        # fall back to substring search on raw_name (any source)
        rows = list(c.execute("""
            SELECT DISTINCT park.slug, park.name_ja, park.prefecture, park.municipality,
                   observation.raw_name AS raw_names, observation.months_bitmap,
                   observation.characteristics, 1 AS source_count
            FROM observation
            JOIN park ON park.id=observation.park_id
            WHERE observation.raw_name LIKE ?
            ORDER BY park.prefecture, park.name_ja
        """, (f"%{name}%",)))
    if not rows:
        print(f"(no observations of '{name}')")
        return
    if sp:
        print(f"=== {sp['common_name_ja']} ({sp['scientific_name'] or '?'}) — observed in {len(rows)} parks ===\n")
    else:
        print(f"=== '{name}' (substring) — {len(rows)} matches ===\n")
    for r in rows:
        months = [m+1 for m in range(12) if (r['months_bitmap'] or 0) & (1<<m)]
        m_str = ",".join(MONTH_NAMES[m] for m in months) if months else "-"
        muni = r['municipality'] or ''
        notes = f"  ({r['characteristics']})" if r['characteristics'] else ""
        sc = f" src={r['source_count']}" if 'source_count' in r.keys() else ""
        print(f"  {r['name_ja']:<24} [{r['prefecture']:<8}] {muni:<14} months={m_str}{sc}{notes}")


def cmd_park(args) -> None:
    slug = args.slug
    c = conn()
    park = c.execute("SELECT * FROM park WHERE slug=?", (slug,)).fetchone()
    if not park:
        sys.exit(f"no park with slug='{slug}'")
    print(f"=== {park['name_ja']} ({park['slug']}) ===")
    print(f"  prefecture: {park['prefecture']}  municipality: {park['municipality']}")
    print(f"  url: {park['official_url']}")
    parking_label = ("駐車場あり" if park['has_parking'] == 1
                     else "駐車場なし" if park['has_parking'] == 0
                     else "駐車場情報なし")
    print(f"  parking: {parking_label}")
    if park['parking_info']:
        info = park['parking_info'].replace('\n', ' ')
        print(f"           {info[:200]}")
    rows = list(c.execute("""
        SELECT ps.raw_names, ps.months_bitmap, ps.characteristics, ps.location_hints,
               ps.observation_count, ps.source_count,
               species.common_name_ja AS sp_ja, species.scientific_name AS sp_sci,
               species.taxon_group AS grp
        FROM park_species ps
        JOIN species ON species.id=ps.species_id
        WHERE ps.park_id=?
        ORDER BY species.taxon_group, species.common_name_ja
    """, (park['id'],)))
    print(f"\n  {len(rows)} unique species:")
    for r in rows:
        months = [m+1 for m in range(12) if (r['months_bitmap'] or 0) & (1<<m)]
        m_str = ",".join(MONTH_NAMES[m] for m in months) if months else "-"
        sci = f"  ({r['sp_sci']})" if r['sp_sci'] else ""
        grp = f"[{r['grp']}]" if r['grp'] else "[?]"
        sname = r['sp_ja'] or r['raw_names'].split("|")[0]
        notes = f"  ({r['characteristics']})" if r['characteristics'] else ""
        src = f" srcs={r['source_count']}" if r['source_count'] > 1 else ""
        print(f"    {sname:<22} {grp:<10} months={m_str:<24}{sci}{src}{notes}")


def cmd_species(args) -> None:
    c = conn()
    sql = """
        SELECT species.common_name_ja, species.scientific_name, species.kingdom,
               species.taxon_group, COUNT(observation.id) AS obs
        FROM species LEFT JOIN observation ON observation.species_id=species.id
    """
    params: list = []
    if args.group:
        sql += " WHERE species.taxon_group=?"
        params.append(args.group)
    sql += " GROUP BY species.id ORDER BY obs DESC"
    if args.limit:
        sql += " LIMIT ?"
        params.append(args.limit)
    rows = list(c.execute(sql, params))
    print(f"=== {len(rows)} species ===")
    for r in rows:
        sci = (r['scientific_name'] or '-')[:35]
        grp = r['taxon_group'] or '?'
        print(f"  {r['obs']:>3} obs  {(r['common_name_ja'] or '?'):<16} {grp:<8}  {sci}")


def cmd_prefecture(args) -> None:
    code = args.code
    c = conn()
    rows = list(c.execute("""
        SELECT park.slug, park.name_ja, park.municipality,
               COUNT(observation.id) AS obs
        FROM park LEFT JOIN observation ON observation.park_id=park.id
        WHERE park.prefecture=? GROUP BY park.id
        ORDER BY obs DESC, park.name_ja
    """, (code,)))
    if not rows:
        sys.exit(f"no parks for prefecture={code}")
    total = sum(r['obs'] for r in rows)
    has = sum(1 for r in rows if r['obs'])
    print(f"=== {code} — {len(rows)} parks ({has} with data, {total} total observations) ===")
    for r in rows:
        muni = r['municipality'] or ''
        marker = " " if r['obs'] else "·"
        print(f"  {marker} {r['obs']:>4}  {r['slug']:<28} {r['name_ja']:<22} {muni}")


def cmd_search(args) -> None:
    needle = f"%{args.substr}%"
    c = conn()
    rows = list(c.execute("""
        SELECT common_name_ja, scientific_name, kingdom, taxon_group
        FROM species
        WHERE common_name_ja LIKE ? OR scientific_name LIKE ?
        ORDER BY common_name_ja
    """, (needle, needle)))
    if not rows:
        print("(no matches)")
        return
    for r in rows:
        sci = r['scientific_name'] or '-'
        grp = r['taxon_group'] or '?'
        print(f"  {(r['common_name_ja'] or '?'):<16} {grp:<8}  {sci}")


def cmd_top(args) -> None:
    """Top species by # of parks they appear in (= most widespread)."""
    c = conn()
    sql = """
      SELECT s.common_name_ja, s.scientific_name, s.taxon_group,
             COUNT(*) AS parks,
             SUM(ps.observation_count) AS obs
      FROM species s JOIN park_species ps ON ps.species_id=s.id
    """
    params: list = []
    if args.group:
        sql += " WHERE s.taxon_group=?"
        params.append(args.group)
    sql += " GROUP BY s.id ORDER BY parks DESC, obs DESC LIMIT ?"
    params.append(args.limit or 30)
    print(f"=== top species{(' [' + args.group + ']') if args.group else ''} by parks ===")
    for r in c.execute(sql, params):
        sci = (r['scientific_name'] or '-')[:35]
        print(f"  {r['parks']:>3} parks  {r['obs']:>5} obs  "
              f"{(r['common_name_ja'] or '?'):<16} {(r['taxon_group'] or '?'):<8}  {sci}")


def cmd_near(args) -> None:
    """Parks near given lat,lon within radius_km. Useful for outing planning."""
    parts = args.coords.split(",")
    if len(parts) != 2:
        sys.exit("coords must be 'lat,lon'")
    lat, lon = float(parts[0]), float(parts[1])
    radius = args.radius_km
    c = conn()
    # crude distance: equirectangular approximation, fine for ≤50 km in Kanto
    rows = list(c.execute("""
        SELECT slug, name_ja, prefecture, lat, lon,
               (lat - ?) * 111.0 AS dy_km,
               (lon - ?) * 111.0 * 0.81 AS dx_km
        FROM park
        WHERE lat IS NOT NULL AND lon IS NOT NULL
    """, (lat, lon)))
    near = []
    for r in rows:
        d = (r['dy_km']**2 + r['dx_km']**2) ** 0.5
        if d <= radius:
            near.append((d, r))
    near.sort(key=lambda x: x[0])
    print(f"=== {len(near)} parks within {radius}km of ({lat}, {lon}) ===")
    for d, r in near[:50]:
        c2 = conn()
        n_obs = c2.execute("SELECT COUNT(*) FROM observation WHERE park_id=(SELECT id FROM park WHERE slug=?)",
                           (r['slug'],)).fetchone()[0]
        print(f"  {d:5.1f}km  {r['slug']:<28} {r['name_ja']:<22} [{r['prefecture']:<8}]  obs={n_obs}")


def cmd_diverse(args) -> None:
    """Parks ranked by species diversity (distinct species)."""
    c = conn()
    rows = list(c.execute("""
        SELECT p.slug, p.name_ja, p.prefecture,
               COUNT(*) AS sp,
               SUM(observation_count) AS obs
        FROM park_species ps JOIN park p ON p.id=ps.park_id
        GROUP BY p.id ORDER BY sp DESC LIMIT ?
    """, (args.limit or 25,)))
    print(f"=== top {len(rows)} parks by species diversity ===")
    for r in rows:
        print(f"  {r['sp']:>4} sp  {r['obs']:>5} obs  "
              f"[{r['prefecture']:<8}] {r['slug']:<28} {r['name_ja']}")


def cmd_plan(args) -> None:
    """Trip planner using deduped park_species. Score combines in-season
    species, total diversity, and inverse distance."""
    parts = args.coords.split(",")
    if len(parts) != 2:
        sys.exit("coords must be 'lat,lon'")
    lat, lon = float(parts[0]), float(parts[1])
    month = int(args.month)
    if not 1 <= month <= 12:
        sys.exit("month must be 1..12")
    bit = 1 << (month - 1)
    radius = args.radius_km
    c = conn()
    parks = list(c.execute("""
        SELECT id, slug, name_ja, prefecture, lat, lon FROM park
        WHERE lat IS NOT NULL AND lon IS NOT NULL
    """))
    candidates: list[dict] = []
    for p in parks:
        dy = (p["lat"] - lat) * 111.0
        dx = (p["lon"] - lon) * 111.0 * 0.81
        d = (dy*dy + dx*dx) ** 0.5
        if d > radius:
            continue
        in_season = c.execute(
            "SELECT COUNT(*) FROM park_species WHERE park_id=? AND (months_bitmap & ?) > 0",
            (p["id"], bit),
        ).fetchone()[0]
        total = c.execute(
            "SELECT COUNT(*) FROM park_species WHERE park_id=?",
            (p["id"],),
        ).fetchone()[0]
        score = in_season + 0.05 * total - 0.5 * d
        candidates.append({"park": p, "in_season": in_season, "total": total,
                           "distance": d, "score": score})
    candidates.sort(key=lambda x: -x["score"])
    print(f"=== trip plan: month {month}, within {radius}km of ({lat},{lon}) ===")
    for c_ in candidates[:args.limit or 5]:
        p = c_["park"]
        print(f"  score={c_['score']:>7.1f}  d={c_['distance']:>5.1f}km  "
              f"in-season={c_['in_season']:>3}  total={c_['total']:>3}  "
              f"[{p['prefecture']:<8}] {p['slug']:<26} {p['name_ja']}")
        samples = list(c.execute("""
            SELECT s.common_name_ja FROM park_species ps
            JOIN species s ON s.id=ps.species_id
            WHERE ps.park_id=? AND (ps.months_bitmap & ?) > 0
            ORDER BY s.taxon_group, s.common_name_ja LIMIT 6
        """, (p["id"], bit)))
        if samples:
            txt = ", ".join(s["common_name_ja"] for s in samples)
            print(f"      e.g.: {txt}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Query the parklife database")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats").set_defaults(fn=cmd_stats)

    p = sub.add_parser("bloom", help="species in season for a given month (1-12)")
    p.add_argument("month")
    p.set_defaults(fn=cmd_bloom)

    p = sub.add_parser("where", help="parks listing a species (Japanese or sci name)")
    p.add_argument("name")
    p.set_defaults(fn=cmd_where)

    p = sub.add_parser("park", help="full info for one park")
    p.add_argument("slug")
    p.set_defaults(fn=cmd_park)

    p = sub.add_parser("species", help="list resolved species")
    p.add_argument("--group", help="filter by taxon_group (bird/insect/tree/...)")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_species)

    p = sub.add_parser("prefecture", help="park summary for a prefecture")
    p.add_argument("code", choices=["tokyo", "kanagawa", "chiba", "saitama"])
    p.set_defaults(fn=cmd_prefecture)

    p = sub.add_parser("search", help="substring search by Japanese or scientific name")
    p.add_argument("substr")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("top", help="most-widespread species (by # of parks listing them)")
    p.add_argument("--group", help="filter by taxon_group (bird/insect/...)")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(fn=cmd_top)

    p = sub.add_parser("near", help="parks near a lat,lon within radius_km")
    p.add_argument("coords", help="e.g. 35.6586,139.7454 (Tokyo Tower)")
    p.add_argument("--radius_km", type=float, default=5.0)
    p.set_defaults(fn=cmd_near)

    p = sub.add_parser("diverse", help="parks ranked by species diversity")
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(fn=cmd_diverse)

    p = sub.add_parser("plan", help="trip planner: best parks within radius for a given month")
    p.add_argument("coords", help="origin lat,lon (e.g. 35.6586,139.7454)")
    p.add_argument("month", help="month 1..12")
    p.add_argument("--radius_km", type=float, default=10.0)
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(fn=cmd_plan)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
