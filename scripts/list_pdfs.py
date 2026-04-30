"""List all cached PDFs and report sizes + any inferred title text."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

for pdf in sorted(RAW.rglob("*.pdf")):
    size_kb = pdf.stat().st_size // 1024
    print(f"  {size_kb:>5} KB  {pdf.relative_to(ROOT)}")
