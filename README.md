# VietRP Studio

Web app for Vietnamese roleplay: character and world library, a gallery, single and world chats driven by a small team of agents, and a passphrase-based vault. Backend is FastAPI + PostgreSQL, frontend is React + Vite, LLM access is OpenRouter only.

Rules for contributors: [`../AGENTS.md`](../AGENTS.md). Architecture: [`../KIEN-TRUC-VIETRP.md`](../KIEN-TRUC-VIETRP.md). Work packages: [`docs/P0-work-packages.md`](docs/P0-work-packages.md).

## Folder map

```
vietrp-studio/
├── backend/    FastAPI app, models, Alembic migrations, tests
├── frontend/   React + Vite app
├── deploy/     systemd units, backup script, setup guide
├── docs/       work packages
└── .env.example
```

## Dev quickstart

Backend (needs Python 3.12 via [uv](https://docs.astral.sh/uv/) and a local PostgreSQL 17):

```
cd backend
uv sync
cp ../.env.example .env        # then fill in DATABASE_URL, VIETRP_SERVER_PEPPER, VIETRP_SESSION_SECRET
uv run alembic upgrade head
uv run uvicorn app.main:app --port 7880
curl http://127.0.0.1:7880/api/health
```

Frontend (Vite dev server on 5173, proxying `/api` to `127.0.0.1:7880`):

```
cd frontend
npm install
npm run dev
```

Quality gates:

```
backend:   uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run pytest
frontend:  npm run lint && npm run typecheck && npm run test && npm run build
```
