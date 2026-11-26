# Stray Animal Rescue System

Geospatial emergency dispatch for injured stray animals. A citizen reports with a photo and a GPS pin; the system ranks the best available responder (vet, NGO, shelter, volunteer) by more than distance — ETA, reliability, workload, capability, service area, location freshness — offers the case to a batch of them with a deadline, and keeps widening the circle until someone accepts or a human is called in.

Design document: [`Stray_Animal_Rescue_System_Blueprint.md`](Stray_Animal_Rescue_System_Blueprint.md).

**Status:** Week 1. FastAPI skeleton with health endpoints, settings from the environment, an async SQLAlchemy engine, and the v2 schema (8 module schemas, 18 tables) as one Alembic migration. No dispatch logic and no frontend yet.

## Requirements

Docker with Compose, [uv](https://docs.astral.sh/uv/), and Git. uv installs Python 3.14 itself.

## Setup

```bash
mkdir -p secrets && tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 > secrets/db_password.txt
docker compose up -d --wait db
cp backend/.env.example backend/.env   # put the same password into DATABASE_URL
uv sync --directory backend
cd backend && uv run alembic upgrade head && uv run pytest
```

`secrets/` and `backend/.env` are gitignored and never leave your machine. The password generator avoids `/` and `+` on purpose, so it can be pasted into the URL without escaping.

Run the API:

```bash
cd backend && uv run uvicorn rescue.main:create_app --factory --reload
```

- http://127.0.0.1:8000/docs — OpenAPI UI
- http://127.0.0.1:8000/health/live — the process is up
- http://127.0.0.1:8000/health/ready — the process **and** the database

## Layout

| Path | What |
|---|---|
| `backend/src/rescue/main.py` | `create_app()`: app factory, lifespan, routes |
| `backend/src/rescue/platform/` | cross-cutting plumbing: `config.py` (the only reader of the environment), `db.py` (engine, `Base`) |
| `backend/migrations/` | Alembic: `env.py` + one linear history in `versions/` |
| `backend/tests/` | pytest; `test_ready.py` needs the db container running |
| `compose.yaml`, `compose.override.yaml`, `db/` | PostgreSQL 18 + PostGIS 3.6 + pgvector image and the dev stack |

## Checks

```bash
uv run --directory backend ruff check . && uv run --directory backend ruff format --check .
npx pyright@1.1.414
cd backend && uv run pytest
```

The same three run in CI (`.github/workflows/ci.yml`), which additionally proves the migration's `downgrade` works.
