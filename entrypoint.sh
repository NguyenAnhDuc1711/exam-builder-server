#!/usr/bin/env sh
# Runs pending Alembic migrations before starting the API — without this,
# a clean `docker-compose up -d` passes /health (which never touches the DB)
# but every other endpoint 500s because no table exists yet (verify.md Gap-1).
set -e

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
