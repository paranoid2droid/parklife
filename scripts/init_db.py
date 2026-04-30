"""Create or upgrade the SQLite database with the parklife schema."""

from pathlib import Path

from parklife import db


def main() -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "parklife.db"
    db.init(path)
    print(f"initialized {path}")


if __name__ == "__main__":
    main()
