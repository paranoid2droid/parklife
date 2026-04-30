"""Highlight endemic / unusual species, especially from 小笠原 (Bonin) and
八丈 (Hachijo). Both archipelagos have unique fauna/flora due to their
isolation.

Output: data/export/ENDEMIC.md
"""
from __future__ import annotations

from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "export" / "ENDEMIC.md"

ISLAND_PARKS = {
    "ogasawara": "小笠原 (Bonin Islands)",
    "hachijo":   "八丈 (Hachijojima)",
    "habushiura": "八丈 (Hachijojima — Habushiura)",
    "takowan":   "神津島 (Kozushima — Tako Bay)",
    "oshima":    "伊豆大島 (Izu Oshima)",
    "shokubutsutayosei-center": "都立 神代 (Plant Diversity Center)",
}


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    lines = ["# 固有種・島嶼特殊種レポート\n"]
    lines.append("Species recorded mainly or exclusively at one of Tokyo's island park areas.\n")
    with db.connect(db_path) as conn:
        for slug, header in ISLAND_PARKS.items():
            park = conn.execute("SELECT id, name_ja FROM park WHERE slug=?", (slug,)).fetchone()
            if not park:
                continue
            lines.append(f"\n## {header} — {park['name_ja']}\n")
            # species at this park that are NOT recorded elsewhere
            rows = list(conn.execute("""
                SELECT s.common_name_ja, s.scientific_name, s.taxon_group,
                       (SELECT COUNT(DISTINCT park_id) FROM observation o2
                          WHERE o2.species_id=s.id) AS park_count
                FROM observation o JOIN species s ON s.id=o.species_id
                WHERE o.park_id=?
                GROUP BY s.id
                HAVING park_count = 1
                ORDER BY s.taxon_group, s.common_name_ja
            """, (park["id"],)))
            if not rows:
                lines.append("(none unique)")
                continue
            lines.append(f"**{len(rows)} species recorded only here.**\n")
            grouped: dict[str, list] = {}
            for r in rows:
                grouped.setdefault(r["taxon_group"] or "?", []).append(r)
            for grp, items in sorted(grouped.items()):
                lines.append(f"\n### [{grp}] ({len(items)})\n")
                for r in items[:25]:
                    sci = r["scientific_name"] or "—"
                    lines.append(f"- **{r['common_name_ja']}** *(_{sci}_)*")
                if len(items) > 25:
                    lines.append(f"- … and {len(items) - 25} more")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
