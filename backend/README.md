# VietRP Studio backend

FastAPI + SQLAlchemy 2 (async) + Alembic. Layering and conventions: see `../../AGENTS.md` section 4.

```
uv sync
uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run pytest
uv run alembic upgrade head          # needs DATABASE_URL
uv run uvicorn app.main:app --host 127.0.0.1 --port 7880
```

Required environment: `DATABASE_URL`, `VIETRP_SERVER_PEPPER` (>= 32 bytes), `VIETRP_SESSION_SECRET` (>= 32 bytes). See `../.env.example` for everything else.

Migration tests run only when `VIETRP_TEST_DATABASE_URL` points at a scratch PostgreSQL database (the test upgrades to head and downgrades to base); otherwise they are skipped.
