"""Fetch and cache a URL, recording it in the `source` table.

- Uses curl_cffi with chrome impersonation (Japanese gov sites reject default TLS).
- Cache layout: data/raw/<prefecture>/<park-slug>/<sha256>.html
- Re-fetching the same URL within a session is a no-op if the file already exists
  AND `force=False`. The DB still gets a new `source` row each call so we can
  trace every observation to a (url, fetched_at) pair.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

UA_IMPERSONATE = "chrome"


def _cache_path(root: Path, prefecture: str, park_slug: str, sha: str) -> Path:
    return root / "data" / "raw" / prefecture / park_slug / f"{sha}.html"


def fetch(
    conn: sqlite3.Connection,
    project_root: Path,
    park_id: int,
    prefecture: str,
    park_slug: str,
    url: str,
    *,
    force: bool = False,
    delay_s: float = 1.0,
) -> tuple[int, Path]:
    """Fetch `url`, cache the body, insert a `source` row, return (source_id, path).

    Politeness: sleep `delay_s` before each network call. Retries once
    with `verify=False` if the cert chain can't be validated (some park
    sites use old/incomplete cert chains).
    """
    time.sleep(delay_s)
    try:
        r = requests.get(url, impersonate=UA_IMPERSONATE, timeout=30)
    except Exception as e:
        if "CertificateVerify" in str(e) or "SSL certificate problem" in str(e):
            r = requests.get(url, impersonate=UA_IMPERSONATE, timeout=30, verify=False)
        else:
            raise
    body = r.content
    sha = hashlib.sha256(body).hexdigest()
    path = _cache_path(project_root, prefecture, park_slug, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    if force or not path.exists():
        path.write_bytes(body)
    rel = str(path.relative_to(project_root))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        """INSERT INTO source (park_id, url, fetched_at, http_status,
                                content_sha256, raw_path)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (park_id, url, now, r.status_code, sha, rel),
    )
    return (cur.lastrowid, path)


def fetch_cached_or_new(
    conn: sqlite3.Connection,
    project_root: Path,
    park_id: int,
    prefecture: str,
    park_slug: str,
    url: str,
    *,
    max_age_days: int = 30,
    delay_s: float = 1.0,
) -> tuple[int, Path]:
    """Use the most recent cached fetch within max_age_days, else fetch fresh."""
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400
    row = conn.execute(
        """SELECT id, fetched_at, raw_path FROM source
           WHERE park_id = ? AND url = ? ORDER BY fetched_at DESC LIMIT 1""",
        (park_id, url),
    ).fetchone()
    if row:
        try:
            ts = datetime.fromisoformat(row["fetched_at"]).timestamp()
        except Exception:
            ts = 0
        path = project_root / row["raw_path"]
        if ts >= cutoff and path.exists():
            return (row["id"], path)
    return fetch(conn, project_root, park_id, prefecture, park_slug, url, delay_s=delay_s)
