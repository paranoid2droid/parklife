# Deploying the thin-client stack

The new stack (`webapp/` SPA + `scripts/serve_api.py` read-only API) is one
self-contained process that serves both the app and `/api/*` from the SQLite DB.
The API path is **stdlib-only**, so the production image is just Python + the
code + `data/parklife.db` — no dependencies to install.

This is the piece that lets the project **retire the legacy 69 MB
`docs/parklife-data.json`** (the last big git artifact) once it's live: the new
stack serves data from the DB on demand instead of shipping a blob.

## Local container test

```bash
docker build -t parklife .
docker run --rm -p 8787:8787 parklife
open http://localhost:8787/
```

The DB is opened immutable read-only (`PARKLIFE_DB_RO=1`) — no `-wal` sidecar,
works on a read-only mount.

## Fly.io (example — Tokyo region, scale-to-zero)

```bash
fly launch --no-deploy     # first run; keep the generated/committed fly.toml
fly deploy
```

`fly.toml` scales to zero when idle and health-checks `/healthz`. 512 MB RAM is
plenty (stdlib server + 245 MB read-only DB).

## Any other container host

The `Dockerfile` is host-agnostic — Render, Railway, and Cloud Run all deploy
straight from it. Set `PORT` if the platform injects its own (the server reads
`PORT`/`HOST` from env). No build args or secrets are required.

## Shipping fresh data

The DB is baked into the image, so **rebuild + redeploy to publish new data**.
The build context pulls the current `data/parklife.db` (rebuild the DB first via
the pipeline in `CLAUDE.md`). Image size ≈ Python base (~120 MB) + DB (~245 MB).

If data updates get frequent, move the DB to a mounted volume / object store and
point `PARKLIFE_DB_RO` at it instead of baking it in — but baking is simplest
and reproducible while data changes infrequently.

## After it's live — retire the legacy blob (permanent git-slim)

Once this stack serves production traffic, drop `docs/parklife-data.json` from
git tracking (add to `.gitignore`) or stop regenerating it. The legacy
`docs/index.html` single-blob demo can then be removed, and `.git` stays
permanently small (the 2026-06-27 history rewrite already removed the
historical copies). See HANDOFF "git-slim" follow-up.
```
