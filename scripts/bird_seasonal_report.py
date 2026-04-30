"""For each bird species with monthly data, show its peak observation
months — a quick reference for "when to see X" or "which migrants are in
right now".

Output: data/export/BIRDS.md
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "export" / "BIRDS.md"

MONTH = ["", "1月", "2月", "3月", "4月", "5月", "6月",
         "7月", "8月", "9月", "10月", "11月", "12月"]


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    lines = ["# 鳥類季節レポート\n",
             "Each bird species and the months it has been observed in our",
             "monitored parks (data: iNaturalist research-grade).\n"]
    with db.connect(db_path) as conn:
        # for each bird species, OR together its months_bitmap across all parks
        rows = list(conn.execute("""
          SELECT s.common_name_ja, s.scientific_name,
                 COUNT(DISTINCT o.park_id) AS parks,
                 SUM(o.months_bitmap) AS bits_sum,
                 GROUP_CONCAT(DISTINCT o.months_bitmap) AS bits_list
          FROM species s JOIN observation o ON o.species_id=s.id
          WHERE s.taxon_group='bird'
          GROUP BY s.id ORDER BY parks DESC
        """))
    by_pattern: dict[str, list] = defaultdict(list)
    for r in rows:
        # OR every distinct bitmap value
        bits = 0
        for b in (r["bits_list"] or "").split(","):
            try:
                bits |= int(b)
            except (TypeError, ValueError):
                continue
        if not bits:
            continue
        months_set = tuple(m+1 for m in range(12) if bits & (1<<m))
        # categorize by pattern
        if len(months_set) == 12:
            cat = "通年"
        elif set(months_set) <= {12, 1, 2, 3}:
            cat = "冬鳥 (winter)"
        elif set(months_set) <= {5, 6, 7, 8, 9}:
            cat = "夏鳥 (summer)"
        elif set(months_set) >= {3, 4, 9, 10, 11}:
            cat = "春秋通過 / 留鳥傾向 (passage/resident-ish)"
        else:
            cat = "その他"
        by_pattern[cat].append((r, months_set))

    for cat in ["通年", "留鳥傾向", "春秋通過 / 留鳥傾向 (passage/resident-ish)",
                "冬鳥 (winter)", "夏鳥 (summer)", "その他"]:
        items = by_pattern.get(cat, [])
        if not items:
            continue
        lines.append(f"\n## {cat}  ({len(items)} 種)\n")
        lines.append("| 名前 | 学名 | 観察月 | 公園数 |")
        lines.append("|---|---|---|---:|")
        for r, months in items[:30]:
            sci = (r["scientific_name"] or "—").replace("|", "/")
            mt = ", ".join(MONTH[m] for m in months)
            lines.append(f"| {r['common_name_ja']} | *{sci}* | {mt} | {r['parks']} |")
        if len(items) > 30:
            lines.append(f"\n*…and {len(items) - 30} more*")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
