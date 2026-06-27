# Production image for the parklife thin-client stack (webapp/ + read-only API).
#
# The API path (scripts/serve_api.py -> parklife/api.py) is 100% stdlib, so the
# image needs NO pip install — just Python, the code, and the baked-in SQLite DB.
# The DB is opened immutable read-only (PARKLIFE_DB_RO=1): no -wal sidecar, works
# on a read-only mount, fastest reads. Rebuild the image to ship fresh data.
#
# Build & run locally:
#   docker build -t parklife .
#   docker run --rm -p 8787:8787 parklife
#   open http://localhost:8787/
FROM python:3.13-slim

WORKDIR /app

# Only what the runtime needs (see .dockerignore for what's excluded).
COPY parklife/ ./parklife/
COPY scripts/__init__.py scripts/serve_api.py ./scripts/
COPY webapp/ ./webapp/
COPY data/parklife.db ./data/parklife.db

ENV HOST=0.0.0.0 \
    PORT=8787 \
    PARKLIFE_DB_RO=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8787

# Stdlib HTTP healthcheck against /healthz.
HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
  CMD python -c "import os,urllib.request,sys; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8787\")}/healthz', timeout=3); " || exit 1

CMD ["python", "-m", "scripts.serve_api"]
