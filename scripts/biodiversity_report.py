"""Generate data/export/REPORT.md — human-readable highlights of the dataset.

Sections:
  - Top biodiversity champions (parks with most species)
  - Endemic / unusual species (small obs count = rare in the dataset)
  - Top species per taxon group
  - Monthly bloom outlook (what's known to be in season)
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "export" / "REPORT.md"

GROUP_LABEL = {
    "bird": "🦜 鳥類", "mammal": "🦌 哺乳類", "reptile": "🦎 爬虫類",
    "amphibian": "🐸 両生類", "insect": "🐛 昆虫", "arachnid": "🕷 クモ類",
    "mollusk": "🐚 軟体動物", "fish": "🐟 魚類",
    "tree": "🌳 樹木", "shrub": "🪴 灌木", "vine": "🍇 藤本",
    "herb": "🌿 草本", "plant": "🌸 植物", None: "❓ 未分類",
}


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    lines: list[str] = []
    with db.connect(db_path) as conn:
        # diversity champions
        lines.append("# parklife biodiversity report\n")

        rows = list(conn.execute("""
            SELECT p.name_ja, p.slug, p.prefecture, p.municipality,
                   COUNT(DISTINCT o.species_id) AS sp,
                   COUNT(o.id) AS obs,
                   p.lat, p.lon
            FROM park p JOIN observation o ON o.park_id=p.id
            WHERE o.species_id IS NOT NULL
            GROUP BY p.id ORDER BY sp DESC LIMIT 25
        """))
        lines.append("## 🌟 多様性チャンピオン (top 25 by species count)\n")
        lines.append("| 順位 | 公園 | 都県 | 種数 | 観察数 |")
        lines.append("|---:|---|---|---:|---:|")
        for i, r in enumerate(rows, 1):
            muni = r["municipality"] or ""
            link = f"[{r['name_ja']}](parks_md/{r['prefecture']}/{r['slug']}.md)"
            lines.append(f"| {i} | {link} ({muni}) | {r['prefecture']} | {r['sp']} | {r['obs']} |")
        lines.append("")

        # by taxon group
        for group in ("bird", "insect", "mammal", "reptile", "amphibian", "fish",
                      "tree", "herb"):
            rows = list(conn.execute("""
              SELECT s.common_name_ja, s.scientific_name,
                     COUNT(DISTINCT o.park_id) AS parks
              FROM species s JOIN observation o ON o.species_id=s.id
              WHERE s.taxon_group=?
              GROUP BY s.id HAVING parks > 0 ORDER BY parks DESC LIMIT 12
            """, (group,)))
            if not rows:
                continue
            label = GROUP_LABEL.get(group, group)
            lines.append(f"## {label} 常連 top 12 (by # of parks)\n")
            lines.append("| 名前 | 学名 | 登場公園数 |")
            lines.append("|---|---|---:|")
            for r in rows:
                sci = (r["scientific_name"] or "—").replace("|", "/")
                lines.append(f"| {r['common_name_ja']} | *{sci}* | {r['parks']} |")
            lines.append("")

        # rare / "only-here" species: species observed in exactly one park
        lines.append("## 🦋 そこだけ種 (species recorded in only ONE park)\n")
        lines.append("Sample (max 30, by taxon group):\n")
        for group in ("bird", "insect", "tree", "herb"):
            rows = list(conn.execute("""
              SELECT s.common_name_ja, s.scientific_name, p.name_ja AS park_name, p.slug, p.prefecture
              FROM species s JOIN observation o ON o.species_id=s.id
                             JOIN park p ON p.id=o.park_id
              WHERE s.taxon_group=?
              GROUP BY s.id HAVING COUNT(DISTINCT o.park_id)=1
              ORDER BY RANDOM() LIMIT 8
            """, (group,)))
            if not rows: continue
            lines.append(f"### {GROUP_LABEL.get(group, group)}\n")
            for r in rows:
                sci = r["scientific_name"] or "—"
                lines.append(f"- **{r['common_name_ja']}** *(_{sci}_)* — only at "
                             f"[{r['park_name']}](parks_md/{r['prefecture']}/{r['slug']}.md)")
            lines.append("")

        # monthly outlook
        lines.append("## 📅 月別開花 (Tokyo park 花の見ごろ data)\n")
        for month in range(1, 13):
            bit = 1 << (month - 1)
            rows = list(conn.execute("""
              SELECT s.common_name_ja, s.scientific_name,
                     COUNT(DISTINCT o.park_id) AS parks
              FROM observation o JOIN species s ON s.id=o.species_id
              WHERE (o.months_bitmap & ?) > 0
              GROUP BY s.id ORDER BY parks DESC LIMIT 10
            """, (bit,)))
            if not rows: continue
            month_ja = ["", "1月", "2月", "3月", "4月", "5月", "6月",
                        "7月", "8月", "9月", "10月", "11月", "12月"][month]
            lines.append(f"### {month_ja}\n")
            top = ", ".join(f"{r['common_name_ja']} ({r['parks']})" for r in rows)
            lines.append(f"- {top}\n")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
