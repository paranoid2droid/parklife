"""Read-only query layer for serving parklife data on demand.

This is the P1-architecture replacement for shipping the whole
``docs/parklife-data.json`` (69 MB) to the browser. The demo's center of
gravity is the *species* records (4-language profiles + photo galleries), which
dominate the blob; parks and park-species pairs are comparatively tiny. So the
access pattern splits naturally:

  * map view        -> a light park index (coords only), or a bbox subset
  * click a park    -> that park's species *summary* cards (no profiles)
  * open a species  -> the full profile + photo gallery, lazily

Nothing here mutates the DB. Every function opens a short-lived read-only
connection via :func:`parklife.db.connect`; all the lookups below are covered
by existing indexes (``idx_park_species_park``, ``idx_species_photo_species``,
``idx_species_profile_species_lang``, ...), so per-request connections are cheap.

The output shapes deliberately mirror ``scripts/export_html.collect_data`` so a
client can consume either source, but keyed by real DB ids (``park.id`` /
``species.id``) instead of the JSON's dense array indices.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "parklife.db"

_PROFILE_LANGS = ("ja", "en", "zh-Hans", "zh-Hant")


def _connect() -> sqlite3.Connection:
    return db.connect(DB_PATH)


# --- taxonomy bucket (kept in sync with scripts/export_html.demo_group) -------

def demo_group(taxon_group: str | None, kingdom: str | None) -> str:
    """Map DB taxonomy to the user-facing demo buckets."""
    if taxon_group in {"plant", "tree", "shrub", "herb", "vine", "fern", "moss"}:
        return "plant"
    if taxon_group in {"bird", "mammal", "fish", "insect", "crustacean", "mollusk", "mushroom"}:
        return taxon_group
    if taxon_group in {"reptile", "amphibian"}:
        return "herp"
    if taxon_group in {"arachnid", "myriapod", "sea_spider", "springtail", "arthropod"}:
        return "arachnid_myriapod"
    if taxon_group in {
        "echinoderm", "cnidarian", "annelid", "flatworm",
        "nematode", "rotifer", "bryozoan", "brachiopod",
    }:
        return "small_aquatic"
    if taxon_group:
        return "unclassified"
    k = (kingdom or "").lower()
    if k == "animalia":
        return "other_animal"
    if k == "plantae":
        return "plant"
    if k == "fungi":
        return "mushroom"
    if k in {"archaea", "bacteria", "chromista", "protozoa"}:
        return ""
    return "unclassified"


def medium_photo_url(url: str | None) -> str | None:
    if not url:
        return url
    return (url
            .replace("/large.", "/medium.")
            .replace("/small.", "/medium.")
            .replace("/square.", "/medium.")
            .replace("/original.", "/medium."))


# --- parks --------------------------------------------------------------------

def _park_row(r: sqlite3.Row, species_count: int | None = None) -> dict:
    out = {
        "id": r["id"],
        "slug": r["slug"],
        "name_ja": r["name_ja"],
        "name_en": r["name_en"],
        "prefecture": r["prefecture"],
        "municipality": r["municipality"],
        "lat": r["lat"],
        "lon": r["lon"],
        "area_m2": r["area_m2"],
        "official_url": r["official_url"],
        "has_parking": r["has_parking"],  # 1=yes, 0=no, None=unknown
    }
    if species_count is not None:
        out["n"] = species_count
    return out


def park_index(bbox: tuple[float, float, float, float] | None = None,
               limit: int | None = None) -> list[dict]:
    """Light park list for the map. Coords only, no species.

    ``bbox`` is ``(min_lon, min_lat, max_lon, max_lat)`` (GeoJSON order). When
    given, only parks with coords inside the box are returned. Parks without
    coords are always excluded from a bbox query (they can't be placed).
    """
    sql = (
        "SELECT p.id, p.slug, p.name_ja, p.name_en, p.prefecture, p.municipality,"
        "       p.lat, p.lon, p.area_m2, p.official_url, p.has_parking,"
        "       (SELECT COUNT(*) FROM park_species ps WHERE ps.park_id = p.id) AS n "
        "FROM park p"
    )
    params: list = []
    where = []
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        where.append("p.lat IS NOT NULL AND p.lon IS NOT NULL")
        where.append("p.lat BETWEEN ? AND ? AND p.lon BETWEEN ? AND ?")
        params += [min_lat, max_lat, min_lon, max_lon]
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY n DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with _connect() as conn:
        return [_park_row(r, r["n"]) for r in conn.execute(sql, params)]


def park_detail(park_id: int) -> dict | None:
    """A park plus its species *summary* cards (no full profiles)."""
    with _connect() as conn:
        p = conn.execute("SELECT * FROM park WHERE id = ?", (park_id,)).fetchone()
        if p is None:
            return None
        rows = conn.execute(
            """
            SELECT s.id, s.scientific_name, s.common_name_ja, s.common_name_en,
                   s.taxon_group, s.kingdom, s.photo_url,
                   ps.months_bitmap, ps.observation_count, ps.source_count
            FROM park_species ps
            JOIN species s ON s.id = ps.species_id
            WHERE ps.park_id = ?
            ORDER BY ps.observation_count DESC, s.scientific_name
            """,
            (park_id,),
        ).fetchall()
        zmap = _zh_alias_map(conn, [r["id"] for r in rows])
        species = [
            {
                "id": r["id"],
                "sci": r["scientific_name"],
                "ja": r["common_name_ja"],
                "en": r["common_name_en"],
                "zh": zmap.get(r["id"], (None, None))[0],
                "zhT": zmap.get(r["id"], (None, None))[1],
                "group": demo_group(r["taxon_group"], r["kingdom"]),
                "tg": r["taxon_group"],
                "k": r["kingdom"],
                "p": medium_photo_url(r["photo_url"]),
                "mb": r["months_bitmap"] or 0,
                "oc": r["observation_count"] or 1,
                "sc": r["source_count"] or 1,
            }
            for r in rows
        ]
        out = _park_row(p, len(species))
        out["species"] = species
        return out


# --- species ------------------------------------------------------------------

def _zh_aliases(conn: sqlite3.Connection, species_id: int) -> tuple[str | None, str | None]:
    rows = conn.execute(
        "SELECT lang, raw_name FROM species_alias "
        "WHERE species_id = ? AND lang IN ('zh-Hans','zh-Hant')",
        (species_id,),
    ).fetchall()
    zh = zht = None
    for r in rows:
        if r["lang"] == "zh-Hans" and not zh:
            zh = r["raw_name"]
        elif r["lang"] == "zh-Hant" and not zht:
            zht = r["raw_name"]
    return zh, zht


def _zh_alias_map(conn: sqlite3.Connection, ids: list[int]) -> dict[int, tuple[str | None, str | None]]:
    """Batch zh-Hans/zh-Hant aliases for many species (one query)."""
    out: dict[int, tuple[str | None, str | None]] = {}
    if not ids:
        return out
    qmarks = ",".join("?" * len(ids))
    for r in conn.execute(
        f"SELECT species_id, lang, raw_name FROM species_alias "
        f"WHERE lang IN ('zh-Hans','zh-Hant') AND species_id IN ({qmarks})",
        ids,
    ):
        zh, zht = out.get(r["species_id"], (None, None))
        if r["lang"] == "zh-Hans" and not zh:
            zh = r["raw_name"]
        elif r["lang"] == "zh-Hant" and not zht:
            zht = r["raw_name"]
        out[r["species_id"]] = (zh, zht)
    return out


def species_detail(species_id: int) -> dict | None:
    """Full species record: names, 4-language profile, photo gallery."""
    with _connect() as conn:
        s = conn.execute("SELECT * FROM species WHERE id = ?", (species_id,)).fetchone()
        if s is None:
            return None
        zh, zht = _zh_aliases(conn, species_id)
        photos = conn.execute(
            "SELECT url, attribution, source_url, license FROM species_photo "
            "WHERE species_id = ? ORDER BY sort_order, id",
            (species_id,),
        ).fetchall()
        imgs = [
            [medium_photo_url(r["url"]), r["attribution"], r["source_url"], r["license"]]
            for r in photos
        ]
        profiles: dict[str, dict] = {}
        for r in conn.execute(
            "SELECT lang, summary, habitat_hint, finding_tips, sources, source_urls "
            "FROM species_profile WHERE species_id = ?",
            (species_id,),
        ):
            profiles[r["lang"]] = {
                "summary": r["summary"],
                "habitat_hint": r["habitat_hint"],
                "finding_tips": r["finding_tips"],
                "sources": r["sources"] or "",
                "source_urls": r["source_urls"] or "",
            }
        return {
            "id": s["id"],
            "sci": s["scientific_name"],
            "ja": s["common_name_ja"],
            "en": s["common_name_en"],
            "zh": zh,
            "zhT": zht,
            "group": demo_group(s["taxon_group"], s["kingdom"]),
            "tg": s["taxon_group"],
            "k": s["kingdom"],
            "tid": s["inat_taxon_id"],
            "p": medium_photo_url(s["photo_url"]),
            "imgs": imgs,
            "pr": profiles,
        }


def species_parks(species_id: int) -> list[dict]:
    """Parks where a species occurs (for the species -> map reverse view)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.slug, p.name_ja, p.name_en, p.prefecture, p.municipality,
                   p.lat, p.lon, p.area_m2, p.official_url, p.has_parking,
                   ps.months_bitmap, ps.observation_count
            FROM park_species ps
            JOIN park p ON p.id = ps.park_id
            WHERE ps.species_id = ?
            ORDER BY ps.observation_count DESC
            """,
            (species_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = _park_row(r)
            d["mb"] = r["months_bitmap"] or 0
            d["oc"] = r["observation_count"] or 1
            out.append(d)
        return out


def species_search(q: str, limit: int = 30) -> list[dict]:
    """Match species by scientific / ja / en / zh name or alias."""
    like = f"%{q}%"
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT s.id, s.scientific_name, s.common_name_ja,
                   s.common_name_en, s.taxon_group, s.kingdom, s.photo_url
            FROM species s
            LEFT JOIN species_alias a ON a.species_id = s.id
            WHERE s.scientific_name LIKE ? OR s.common_name_ja LIKE ?
               OR s.common_name_en LIKE ? OR a.raw_name LIKE ?
            ORDER BY
              (SELECT COUNT(*) FROM park_species ps WHERE ps.species_id = s.id) DESC
            LIMIT ?
            """,
            (like, like, like, like, limit),
        ).fetchall()
        zmap = _zh_alias_map(conn, [r["id"] for r in rows])
        return [
            {
                "id": r["id"],
                "sci": r["scientific_name"],
                "ja": r["common_name_ja"],
                "en": r["common_name_en"],
                "zh": zmap.get(r["id"], (None, None))[0],
                "zhT": zmap.get(r["id"], (None, None))[1],
                "group": demo_group(r["taxon_group"], r["kingdom"]),
                "p": medium_photo_url(r["photo_url"]),
            }
            for r in rows
        ]


@lru_cache(maxsize=1)
def stats() -> dict:
    with _connect() as conn:
        one = lambda sql: conn.execute(sql).fetchone()[0]
        return {
            "parks": one("SELECT COUNT(*) FROM park"),
            "parks_with_coords": one(
                "SELECT COUNT(*) FROM park WHERE lat IS NOT NULL AND lon IS NOT NULL"),
            "species": one("SELECT COUNT(*) FROM species"),
            "pairs": one("SELECT COUNT(*) FROM park_species"),
            "profiles": one("SELECT COUNT(DISTINCT species_id) FROM species_profile"),
        }
