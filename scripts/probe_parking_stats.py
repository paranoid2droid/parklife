"""Show parking coverage by prefecture + sample of unknowns."""
from parklife import db
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    print("=== by prefecture ===")
    for r in conn.execute("""
      SELECT prefecture,
             SUM(CASE WHEN has_parking=1 THEN 1 ELSE 0 END) AS yes,
             SUM(CASE WHEN has_parking=0 THEN 1 ELSE 0 END) AS no,
             SUM(CASE WHEN has_parking IS NULL THEN 1 ELSE 0 END) AS unk
      FROM park GROUP BY prefecture
    """):
        print(f"  {r[0]:<10} yes={r[1]:>4} no={r[2]:>3} unknown={r[3]:>4}")

    print("\n=== sample of NO (parking explicitly absent) ===")
    for r in conn.execute("SELECT slug, name_ja, parking_info FROM park WHERE has_parking=0 LIMIT 10"):
        print(f"  {r[0]:<22} {r[1]:<24}  '{(r[2] or '')[:80]}'")

    print("\n=== sample of YES (sanity check) ===")
    for r in conn.execute("SELECT slug, name_ja, parking_info FROM park WHERE has_parking=1 LIMIT 5"):
        print(f"  {r[0]:<22} {r[1]:<24}  '{(r[2] or '')[:80]}'")

    print("\n=== unknown by prefecture (slug + name) ===")
    for pref in ("tokyo", "kanagawa", "chiba", "saitama"):
        rows = list(conn.execute(
          "SELECT slug, name_ja FROM park WHERE has_parking IS NULL AND prefecture=? LIMIT 6",
          (pref,)))
        if rows:
            print(f"  -- {pref} --")
            for r in rows:
                print(f"    {r[0]:<22} {r[1]}")
