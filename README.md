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

### Docker services

```bash
docker compose up postgres redis
```

Switch `DATABASE_URL` to Postgres when needed.
