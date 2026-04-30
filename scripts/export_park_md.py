"""Generate one Markdown page per park summarising its biodiversity.

Output: data/export/parks_md/<prefecture>/<slug>.md
Index:  data/export/parks_md/INDEX.md
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "export" / "parks_md"

MONTH_JA = ["", "1月", "2月", "3月", "4月", "5月", "6月",
            "7月", "8月", "9月", "10月", "11月", "12月"]


def fmt_months(b: int | None) -> str:
    if not b:
        return "通年/不明"
    months = [MONTH_JA[m+1] for m in range(12) if b & (1<<m)]
    return ", ".join(months)


GROUP_LABEL = {
    "bird": "🦜 鳥類", "mammal": "🦌 哺乳類", "reptile": "🦎 爬虫類",
    "amphibian": "🐸 両生類", "insect": "🐛 昆虫", "arachnid": "🕷 クモ類",
    "mollusk": "🐚 軟体動物", "fish": "🐟 魚類",
    "tree": "🌳 樹木", "shrub": "🪴 灌木", "vine": "🍇 藤本",
    "herb": "🌿 草本", "fern": "🌿 シダ", "moss": "🌱 蘚苔",
    "plant": "🌸 植物", None: "❓ 未分類", "?": "❓ 未分類",
}
GROUP_ORDER = ["bird", "mammal", "reptile", "amphibian", "fish",
               "insect", "arachnid", "mollusk",
               "tree", "shrub", "vine", "herb", "fern", "moss", "plant",
               None, "?"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    db_path = ROOT / "data" / "parklife.db"
    written = 0
    by_pref: dict[str, list[tuple[str, str, int]]] = defaultdict(list)

    with db.connect(db_path) as conn:
        parks = list(conn.execute("""
            SELECT id, slug, name_ja, prefecture, municipality, official_url, lat, lon
            FROM park ORDER BY prefecture, slug
        """))
        for p in parks:
            # Use the deduped park_species table for the main listing
            obs = list(conn.execute("""
                SELECT ps.raw_names, ps.months_bitmap, ps.location_hints, ps.characteristics,
                       ps.observation_count, ps.source_count,
                       s.common_name_ja, s.scientific_name, s.taxon_group
                FROM park_species ps LEFT JOIN species s ON s.id=ps.species_id
                WHERE ps.park_id=?
                ORDER BY s.taxon_group, s.common_name_ja, ps.raw_names
            """, (p["id"],)))
            grouped: dict[str | None, list] = defaultdict(list)
            for r in obs:
                # synthesize a 'raw_name' for the existing template (first of the
                # pipe-joined list)
                raw_name = (r["raw_names"] or "").split("|")[0]
                grouped[r["taxon_group"]].append({
                    "raw_name": raw_name,
                    "months_bitmap": r["months_bitmap"],
                    "location_hint": r["location_hints"],
                    "characteristics": r["characteristics"],
                    "common_name_ja": r["common_name_ja"],
                    "scientific_name": r["scientific_name"],
                    "taxon_group": r["taxon_group"],
                    "source_count": r["source_count"],
                })

            lines: list[str] = []
            lines.append(f"# {p['name_ja']}")
            lines.append("")
            meta = []
            meta.append(f"**所在**: {p['prefecture']} / {p['municipality'] or '-'}")
            if p["lat"] and p["lon"]:
                meta.append(f"**位置**: {p['lat']:.4f}, {p['lon']:.4f}")
            if p["official_url"]:
                meta.append(f"**公式**: <{p['official_url']}>")
            lines.append(" | ".join(meta))
            lines.append("")
            total = sum(len(v) for v in grouped.values())
            lines.append(f"**観察記録**: {total} 件 / {len(grouped)} カテゴリ")
            lines.append("")

            for grp in GROUP_ORDER:
                items = grouped.get(grp, [])
                if not items:
                    continue
                label = GROUP_LABEL.get(grp, str(grp))
                lines.append(f"## {label} ({len(items)})")
                lines.append("")
                lines.append("| 名前 | 学名 | 月 | 備考 |")
                lines.append("|---|---|---|---|")
                for r in sorted(items, key=lambda x: x["common_name_ja"] or x["raw_name"]):
                    name_ja = r["common_name_ja"] or r["raw_name"]
                    sci = (r["scientific_name"] or "—").replace("|", "/")
                    months = fmt_months(r["months_bitmap"])
                    loc = r["location_hint"] or ""
                    char = r["characteristics"] or ""
                    note = "; ".join(x for x in (loc, char) if x).replace("|", "/").replace("\n", " ")
                    lines.append(f"| {name_ja} | *{sci}* | {months} | {note[:80]} |")
                lines.append("")

            target = OUT / p["prefecture"] / f"{p['slug']}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(lines), encoding="utf-8")
            written += 1
            by_pref[p["prefecture"]].append((p["slug"], p["name_ja"], total))

    # index
    idx = [
        "# 公園一覧",
        "",
        f"全 {sum(len(v) for v in by_pref.values())} 公園、 "
        f"{sum(t for v in by_pref.values() for _,_,t in v)} 件の観察。",
        "",
    ]
    for pref in ("tokyo", "kanagawa", "chiba", "saitama"):
        items = sorted(by_pref.get(pref, []), key=lambda x: -x[2])
        if not items:
            continue
        idx.append(f"## {pref}  ({len(items)} 公園)")
        idx.append("")
        for slug, name, total in items:
            idx.append(f"- [`{slug}`]({pref}/{slug}.md) {name} — {total} 観察")
        idx.append("")
    (OUT / "INDEX.md").write_text("\n".join(idx), encoding="utf-8")
    print(f"wrote {written} park pages + INDEX.md to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
