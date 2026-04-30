"""Per-park: check ALL cached HTML files for parking section, not just largest."""
from pathlib import Path
import sys
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent

KEYWORDS = ("駐車場", "パーキング")


def find_in_html(html: bytes) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tag in soup.find_all(["h2", "h3", "h4", "h5"]):
        text = " ".join(tag.get_text().split())
        if any(k in text for k in KEYWORDS) and len(text) <= 30:
            out.append((tag.name, text))
    return out


def main(slug: str) -> None:
    for prefecture in ("tokyo", "kanagawa", "chiba", "saitama"):
        d = ROOT / "data" / "raw" / prefecture / slug
        if not d.is_dir():
            continue
        for h in sorted(d.glob("*.html")):
            size = h.stat().st_size
            hits = find_in_html(h.read_bytes())
            print(f"  {h.name[:25]:<26} {size:>7}B  hits={hits}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kasairinkai")
