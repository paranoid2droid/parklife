# webapp — thin-client SPA

A lightweight single-page app that fetches park/species data **on demand** from
the read-only API (`scripts/serve_api.py`) instead of downloading the whole
69 MB `docs/parklife-data.json`. This is the productization P1 front-end that
makes the git-slim possible: the big blob no longer needs to ship to the browser.

## Run (one command serves both API + app, same origin)

```bash
.venv/bin/python -m scripts.serve_api          # http://127.0.0.1:8787
# PORT=9000 HOST=0.0.0.0 .venv/bin/python -m scripts.serve_api
```

Open <http://127.0.0.1:8787/>.

## Data flow (why it's thin)

| action            | request                       | payload   |
|-------------------|-------------------------------|-----------|
| initial map       | `GET /api/parks`              | ~0.8 MB (all 3,064 markers; gzip ~150 KB) |
| click a park      | `GET /api/parks/<id>`         | ~150–180 KB (species summary cards) |
| open a species    | `GET /api/species/<id>`       | ~5 KB (4-lang profile + photo gallery) |
| search box        | `GET /api/search?q=...`       | small |

vs. the old demo's single **69 MB** up-front fetch.

## Files

- `index.html` — shell + inline CSS, loads Leaflet + MarkerCluster from unpkg.
- `app.js` — all logic: map/markers, park panel, species modal, search, ja/en/zh/zhT toggle.
  API base defaults to same-origin `/api`; override with `?api=<base>` for a split deploy.

## Test

`/tmp/pl_e2e.py` drives the full click-flow through system Chrome (playwright,
`channel="chrome"` — no browser download). Start the server first, then run it.

## Ported from the old demo

- **Sort** (record count / name / scientific) — per-park species panel.
- **Month filter** — seasonal soft filter (species with no month data pass through).
- **Group toggle** — click a group header to collapse/expand its grid.
- **Parking filter** — map control ("🅿️ Parking only") filters markers to `has_parking==1`.
- **Park-local photos** — the species modal prepends `park_species_photo` images
  for the (park, species) pair, badged "📍 Photos at this park", before the
  global species hero gallery. Endpoint: `GET /api/parks/<pid>/photos/<sid>`.

- **Show more** — each group caps at 48 cards with "show N more" / "show all"
  buttons, so a 600-species park stays light on mobile.

## Net-new (beyond the old demo)

- **Species → map reverse view** — the species modal has "🗺 show parks with
  this species": plots/highlights every park where it occurs (via
  `/api/species/<id>/parks`), fits bounds, with a banner + "back to all parks".

## Ideas not yet built

URL deep-linking (shareable park/species links), viewport-driven marker loading
(`/api/parks?bbox=`) for very dense zooms.
