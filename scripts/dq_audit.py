"""Read-only data-quality audit of data/parklife.db.

Runs the recurring integrity checks in one command so every ingestion/normalization
pass can self-check. Writes nothing. Exit code is non-zero when a HARD defect is
found (so it can gate the autonomous queue), zero when only soft warnings remain.

Checks:
  1. Wrong-photo contamination — a photo URL attached to >1 species. The classic
     defect: the ensure_inat_taxon `best_match results[0]` fallback (or a later
     tid-NULL that left gallery rows behind) makes one taxon's photos appear under
     another. Benign sub-cases are classified out: a genus-rank row sharing photos
     with a member species, or a single incidental shared observation. A SUSPECT
     pair = two binomial species sharing >=2 photos (near-gallery overlap) → HARD.
  2. tid collisions — same inat_taxon_id on >1 species row → HARD.
  3. microbe / noise kingdoms leaking into park_species (dedupe should drop) → HARD.
  4. captive-suppression leak — a data/suppressed_species.json id still in
     park_species (dedupe should have dropped it) → HARD.
  5. orphan FKs in species_photo / species_alias / park_species → HARD.
  6. placeholder / ascii / kingdom-junk ja-names on visible species → SOFT warning
     (honest 「和名なし」 labels are allowed).

Usage:
  python -m scripts.dq_audit            # report; exit 1 if any HARD defect
  python -m scripts.dq_audit --quiet    # only print HARD defects + the summary
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"
SUPPRESSED = ROOT / "data" / "suppressed_species.json"

# ja suffixes that mark a non-species rank (genus/family/…); such a row legitimately
# shares a photo with a member species, so those pairs are benign.
RANK_SUFFIXES = ("属", "科", "亜科", "目", "亜目", "族", "連", "類")


def _is_higher_rank(ja: str | None, sci: str | None) -> bool:
    if ja and ja.endswith(RANK_SUFFIXES):
        return True
    # a scientific name with no space is genus-or-higher (not a binomial species)
    if sci and " " not in sci.strip():
        return True
    return False


def main(quiet: bool = False) -> int:
    conn = db.connect(DB)
    hard = 0  # count of hard defects
    out: list[str] = []

    def emit(line: str = "", *, soft: bool = False) -> None:
        if quiet and soft:
            return
        out.append(line)

    # ---- 1. wrong-photo contamination -------------------------------------
    pairs = conn.execute(
        """SELECT a.species_id AS a, b.species_id AS b, COUNT(*) AS shared
             FROM species_photo a JOIN species_photo b
               ON a.url = b.url AND a.species_id < b.species_id
            GROUP BY a.species_id, b.species_id
            ORDER BY shared DESC"""
    ).fetchall()

    def sp(sid: int):
        r = conn.execute(
            "SELECT common_name_ja, scientific_name, kingdom FROM species WHERE id=?",
            (sid,),
        ).fetchone()
        return (r["common_name_ja"], r["scientific_name"], r["kingdom"]) if r else (None, None, None)

    suspect = []
    benign = 0
    for pr in pairs:
        ja1, sc1, k1 = sp(pr["a"])
        ja2, sc2, k2 = sp(pr["b"])
        higher = _is_higher_rank(ja1, sc1) or _is_higher_rank(ja2, sc2)
        if higher or pr["shared"] < 2:
            benign += 1
            continue
        suspect.append((pr["a"], pr["b"], pr["shared"], ja1, sc1, k1, ja2, sc2, k2))

    emit("=" * 64)
    emit(f"1. WRONG-PHOTO CONTAMINATION: {len(pairs)} photo-sharing pairs "
         f"({benign} benign genus/incidental, {len(suspect)} SUSPECT)")
    for a, b, sh, ja1, sc1, k1, ja2, sc2, k2 in suspect:
        cross = " CROSS-KINGDOM" if k1 != k2 else ""
        emit(f"   [SUSPECT{cross}] shared={sh}")
        emit(f"       id{a} {ja1} / {sc1} [{k1}]")
        emit(f"       id{b} {ja2} / {sc2} [{k2}]")
    hard += len(suspect)

    # ---- 2. tid collisions -------------------------------------------------
    tidcol = conn.execute(
        """SELECT inat_taxon_id, COUNT(*) n FROM species
            WHERE inat_taxon_id IS NOT NULL
            GROUP BY inat_taxon_id HAVING n > 1 ORDER BY n DESC"""
    ).fetchall()
    emit("=" * 64)
    emit(f"2. TID COLLISIONS: {len(tidcol)}")
    for r in tidcol[:20]:
        rows = conn.execute(
            "SELECT common_name_ja, scientific_name FROM species WHERE inat_taxon_id=?",
            (r["inat_taxon_id"],),
        ).fetchall()
        emit(f"   tid={r['inat_taxon_id']} x{r['n']}: "
             + " | ".join(f"{x['common_name_ja']}({x['scientific_name']})" for x in rows))
    hard += len(tidcol)

    # ---- 3. microbe / noise kingdoms in park_species ----------------------
    noise = conn.execute(
        """SELECT s.kingdom, COUNT(DISTINCT ps.species_id) n
             FROM park_species ps JOIN species s ON s.id = ps.species_id
            WHERE s.kingdom IN ('bacteria', 'virus', 'archaea')
            GROUP BY s.kingdom"""
    ).fetchall()
    emit("=" * 64)
    emit(f"3. MICROBE NOISE IN park_species: {sum(r['n'] for r in noise)}")
    for r in noise:
        emit(f"   {r['kingdom']}: {r['n']}")
    hard += sum(r["n"] for r in noise)

    # ---- 4. captive-suppression leak --------------------------------------
    leaked = []
    if SUPPRESSED.exists():
        data = json.loads(SUPPRESSED.read_text(encoding="utf-8"))
        ids = [e["species_id"] for e in data] if isinstance(data, list) else list(data.keys())
        for sid in ids:
            n = conn.execute("SELECT COUNT(*) FROM park_species WHERE species_id=?", (sid,)).fetchone()[0]
            if n:
                leaked.append((sid, n))
    emit("=" * 64)
    emit(f"4. CAPTIVE-SUPPRESSION LEAK: {len(leaked)} of "
         f"{len(ids) if SUPPRESSED.exists() else 0} suppressed still in park_species")
    for sid, n in leaked:
        emit(f"   id{sid}: {n} park_species rows (dedupe should have dropped)")
    hard += len(leaked)

    # ---- 5. orphan FKs -----------------------------------------------------
    emit("=" * 64)
    emit("5. ORPHAN FKs")
    for tbl in ("species_photo", "species_alias", "park_species"):
        o = conn.execute(
            f"SELECT COUNT(*) FROM {tbl} t "
            f"WHERE NOT EXISTS(SELECT 1 FROM species s WHERE s.id = t.species_id)"
        ).fetchone()[0]
        emit(f"   {tbl}: {o}")
        hard += o

    # ---- 6. placeholder ja-names (soft) -----------------------------------
    junk = conn.execute(
        """SELECT common_name_ja, scientific_name FROM species s
            WHERE common_name_ja IS NOT NULL
              AND (common_name_ja GLOB '*[a-zA-Z]*'
                   OR common_name_ja LIKE '%動物界%' OR common_name_ja LIKE '%植物界%'
                   OR common_name_ja LIKE '%菌界%')
              AND common_name_ja NOT LIKE '%和名なし%'
              AND EXISTS(SELECT 1 FROM park_species ps WHERE ps.species_id = s.id)"""
    ).fetchall()
    emit("=" * 64, soft=True)
    emit(f"6. PLACEHOLDER/ASCII ja-names on visible species (soft): {len(junk)}", soft=True)
    for r in junk[:20]:
        emit(f"   {r['common_name_ja']}  <-  {r['scientific_name']}", soft=True)

    conn.close()

    out.append("=" * 64)
    status = "CLEAN" if hard == 0 else f"{hard} HARD DEFECT(S)"
    out.append(f"RESULT: {status}"
               + (f"  (+{len(junk)} soft ja-name warnings)" if junk else ""))
    print("\n".join(out))
    return 0 if hard == 0 else 1


if __name__ == "__main__":
    sys.exit(main(quiet="--quiet" in sys.argv[1:]))
