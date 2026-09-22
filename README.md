# Agent Marketplace

An AI-assisted, agent-ready C2C classifieds marketplace with:

- `FastAPI` backend
- `Next.js` public web
- `Flutter` mobile scaffold
- AI listing autofill with OpenAI vision + structured outputs
- AI sale-image generation with GPT Image
- public REST/OpenAPI plus MCP tools for agents

## Quick start

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example .env
uvicorn app.main:app --reload
```

The backend defaults to local SQLite for development and serves uploaded/generated media from `/media`.

### Web

```bash
cd web
npm install
npm run dev
```

Set:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

For remote testing, set backend `BASE_URL` and `FRONTEND_URL` plus the two web env vars to the externally reachable hostnames.

### MCP server

```bash
cd backend
source .venv/bin/activate
fastmcp run app/mcp_server.py:mcp --transport http --port 9000
```

This exposes the MCP endpoint at `http://localhost:9000/mcp`.

Agents prepare changes with scoped PATs; sellers decide proposals with their
interactive sign-in token. See [approval integrity and verification](backend/APPROVALS.md)
for REST/MCP scope rules, replay behavior, transaction boundaries and legacy migration.

### Docker services

```bash
docker compose up postgres redis
```

The backend includes `asyncpg==0.31.0`. Use the explicit async SQLAlchemy URL
when switching from SQLite to PostgreSQL:

```bash
export DATABASE_URL='postgresql+asyncpg://marketplace:marketplace@127.0.0.1:5432/marketplace'
# PowerShell: $env:DATABASE_URL='postgresql+asyncpg://marketplace:marketplace@127.0.0.1:5432/marketplace'
cd backend
uvicorn app.main:app
```

The example credentials match the local Compose service; supply separate
credentials for other environments. Startup applies Alembic migrations.
Changing the URL selects a different database; it does not transfer SQLite data.

### PostgreSQL API verification

On a disposable PostgreSQL server, use a role with `CREATEDB` permission:

```bash
cd backend
export POSTGRES_TEST_URL='postgresql+asyncpg://marketplace:marketplace@127.0.0.1:5432/marketplace'
# PowerShell uses $env:POSTGRES_TEST_URL='postgresql+asyncpg://...'
python scripts/verify_postgres.py
```

The script creates a uniquely named test database, migrates it from an empty
schema, exercises registration, draft review/publication, mock checkout,
scoped grants, human approval, replay and receipts, then removes only that
generated database. It never migrates or clears the database named in the URL.
Model calls and payment are explicitly mocked; no `.env` file is loaded.
CI runs the same check against PostgreSQL 16 in addition to the SQLite suite.

Locally verified on 2026-09-23 with PostgreSQL 16.13 and asyncpg 0.31.0:
all four migrations and twelve API checks passed. This is functional verification,
not a concurrency benchmark or production deployment claim.
Driver reference: [asyncpg release](https://pypi.org/project/asyncpg/0.31.0/).
