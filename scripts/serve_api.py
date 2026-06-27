"""Lightweight read-only JSON API over data/parklife.db.

Prototype for the productization P1 spatial backend: serves parks / species on
demand so the browser never fetches the whole 69 MB ``parklife-data.json``.
Stdlib only (``http.server``) — no FastAPI/uvicorn dependency for the prototype;
swap in an ASGI server later if/when this graduates to production.

Run:
    .venv/bin/python -m scripts.serve_api            # 127.0.0.1:8787
    PORT=9000 .venv/bin/python -m scripts.serve_api

Endpoints (all JSON, CORS-open for local dev):
    GET /api/stats
    GET /api/parks                         -> light index (all parks)
    GET /api/parks?bbox=minLon,minLat,maxLon,maxLat[&limit=N]
    GET /api/parks/<id>                    -> park + species summary cards
    GET /api/species/<id>                  -> full profile + photo gallery
    GET /api/species/<id>/parks            -> parks where the species occurs
    GET /api/search?q=<text>[&limit=N]     -> species name search
    GET /healthz
"""

from __future__ import annotations

import gzip
import json
import mimetypes
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from parklife import api

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8787"))

# Static thin-client SPA lives in webapp/ (sibling of scripts/). Served at root
# so one process hosts both the app and the /api endpoints (same origin → the
# browser fetch() needs no CORS dance).
ROOT = Path(__file__).resolve().parent.parent
WEBAPP_DIR = ROOT / "webapp"


class Handler(BaseHTTPRequestHandler):
    server_version = "parklife-api/0.1"

    # --- helpers -------------------------------------------------------------
    def _accepts_gzip(self) -> bool:
        return "gzip" in self.headers.get("Accept-Encoding", "")

    def _send(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        gz = len(body) > 1024 and self._accepts_gzip()
        if gz:
            body = gzip.compress(body, 6)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: int, msg: str) -> None:
        self._send({"error": msg}, status)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        query = parse_qs(parsed.query)
        try:
            self._route(parts, query)
        except BrokenPipeError:
            pass
        except Exception:  # noqa: BLE001 - log server-side, don't leak internals
            traceback.print_exc()
            self._error(500, "internal error")

    def _send_static(self, rel: str) -> None:
        """Serve a file from webapp/ (the SPA). Path-traversal safe."""
        if not rel or rel.endswith("/"):
            rel = (rel + "index.html") if rel else "index.html"
        target = (WEBAPP_DIR / rel).resolve()
        if WEBAPP_DIR not in target.parents and target != WEBAPP_DIR:
            return self._error(403, "forbidden")
        if not target.is_file():
            return self._error(404, "not found")
        ext_types = {".webmanifest": "application/manifest+json"}
        ctype = (ext_types.get(target.suffix)
                 or mimetypes.guess_type(str(target))[0]
                 or "application/octet-stream")
        data = target.read_bytes()
        compressible = (ctype.startswith("text/")
                        or ctype in ("application/manifest+json", "image/svg+xml",
                                     "application/javascript", "text/javascript"))
        gz = compressible and len(data) > 1024 and self._accepts_gzip()
        if gz:
            data = gzip.compress(data, 6)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    # --- routing -------------------------------------------------------------
    def _route(self, parts: list[str], query: dict) -> None:
        if parts == ["healthz"]:
            return self._send({"ok": True})
        # Non-API paths → static SPA files from webapp/.
        if not parts or parts[0] != "api":
            return self._send_static("/".join(parts))
        if parts == ["api", "stats"]:
            return self._send(api.stats())

        if parts == ["api", "parks"]:
            bbox = None
            if "bbox" in query:
                try:
                    nums = [float(x) for x in query["bbox"][0].split(",")]
                    if len(nums) != 4:
                        raise ValueError
                    bbox = (nums[0], nums[1], nums[2], nums[3])
                except ValueError:
                    return self._error(400, "bbox must be minLon,minLat,maxLon,maxLat")
            limit = int(query["limit"][0]) if "limit" in query else None
            return self._send(api.park_index(bbox=bbox, limit=limit))

        if len(parts) == 3 and parts[:2] == ["api", "parks"]:
            pid = self._as_int(parts[2])
            if pid is None:
                return self._error(400, "park id must be an integer")
            d = api.park_detail(pid)
            return self._send(d) if d else self._error(404, "park not found")

        # /api/parks/<pid>/photos/<sid> -> park-local photos for a pair
        if (len(parts) == 5 and parts[:2] == ["api", "parks"] and parts[3] == "photos"):
            pid = self._as_int(parts[2])
            sid = self._as_int(parts[4])
            if pid is None or sid is None:
                return self._error(400, "park and species ids must be integers")
            return self._send(api.pair_photos(pid, sid))

        if parts == ["api", "search"]:
            q = query.get("q", [""])[0].strip()
            if not q:
                return self._error(400, "q is required")
            limit = int(query["limit"][0]) if "limit" in query else 30
            return self._send(api.species_search(q, limit=limit))

        if len(parts) >= 3 and parts[:2] == ["api", "species"]:
            sid = self._as_int(parts[2])
            if sid is None:
                return self._error(400, "species id must be an integer")
            if len(parts) == 3:
                d = api.species_detail(sid)
                return self._send(d) if d else self._error(404, "species not found")
            if len(parts) == 4 and parts[3] == "parks":
                return self._send(api.species_parks(sid))

        return self._error(404, "no such route")

    @staticmethod
    def _as_int(s: str) -> int | None:
        try:
            return int(s)
        except ValueError:
            return None

    def log_message(self, fmt, *args) -> None:  # quieter logs
        return


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"parklife API on http://{HOST}:{PORT}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
        httpd.shutdown()


if __name__ == "__main__":
    main()
