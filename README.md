# FinAlly — AI Trading Workstation

[![Tests](https://github.com/Paul-Orlando/multi_agent_trading_app/actions/workflows/tests.yml/badge.svg)](https://github.com/Paul-Orlando/multi_agent_trading_app/actions/workflows/tests.yml)

> **Demo only.** Simulated prices and virtual money. Nothing here is investment advice.

An AI-powered trading workstation that streams live market data, simulates portfolio trading, and integrates an LLM chat assistant that can analyze positions and execute trades via natural language.

## Features

- **Live price streaming** via SSE with green/red flash animations
- **Simulated portfolio** — $10k virtual cash, market orders, instant fills
- **Portfolio visualizations** — heatmap (treemap), P&L chart, positions table
- **AI chat assistant** — analyzes holdings, suggests and auto-executes trades
- **Watchlist management** — track tickers manually or via AI
- **Dark terminal aesthetic** — Bloomberg-inspired, data-dense layout

## Architecture

One FastAPI server serving everything on port 8000:

- **Frontend**: Next.js (static export) with TypeScript and Tailwind CSS
- **Backend**: FastAPI (Python/uv) with SSE streaming
- **Database**: SQLite with lazy initialization
- **AI**: LiteLLM → OpenRouter, `openai/gpt-oss-120b` served only by Cerebras, with structured outputs
- **Market data**: Built-in GBM simulator (default) or Massive API (optional)

## Quick Start

Needs Python 3.12 with [uv](https://docs.astral.sh/uv/) and Node 20.

```bash
# Configure
cp .env.example .env
# Set OPENROUTER_API_KEY in .env (or set LLM_MOCK=true to try it without a key)

# Build the frontend (static export to frontend/out)
cd frontend
npm ci
npm run build
cd ..

# Run the backend, which serves the API and the built frontend on port 8000
cd backend
uv sync
FINALLY_STATIC_DIR=../frontend/out uv run uvicorn app.main:app --port 8000
# PowerShell: $env:FINALLY_STATIC_DIR="../frontend/out"; uv run uvicorn app.main:app --port 8000

# Open http://localhost:8000
```

For frontend development with hot reload, run the backend as above and `npm run dev` in `frontend/` (http://localhost:3000, which proxies `/api` to port 8000).

The live site runs on Railway, built with Railpack (see `railway.toml`, `railpack.json` and `deploy/RAILWAY.md`).

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for AI chat |
| `MASSIVE_API_KEY` | No | Massive (Polygon.io) key for real market data; omit to use simulator |
| `LLM_MOCK` | No | `false` by default; set `true` for deterministic mock LLM responses (testing) |
| `OPENROUTER_MODEL` | No | AI model on OpenRouter (default `openai/gpt-oss-120b`) |
| `OPENROUTER_PROVIDER` | No | The only provider allowed to serve it, no fallbacks (default `cerebras`) |
| `OPENROUTER_MAX_TOKENS` | No | Reply cap per AI call (default 1500) |
| `OPENROUTER_TIMEOUT` | No | AI request timeout in seconds (default 30) |
| `APP_URL` | No | Site address sent to OpenRouter as the app label (default: the Railway domain) |
| `RISK_*` | No | Risk limit overrides, e.g. `RISK_MAX_POSITION_PCT` (defaults listed in `.env.example`) |
| `RATE_LIMIT_CHAT_PER_HOUR`, `RATE_LIMIT_TRADES_PER_HOUR` | No | Per-address usage limits (defaults 15 and 20) |
| `MAX_WATCHLIST` | No | Maximum watchlist size (default 50) |

## Project Structure

```
finally/
├── frontend/    # Next.js static export
├── backend/     # FastAPI uv project
├── docs/        # Redesign plan; earlier planning docs in docs/history/
├── test/        # Playwright E2E tests
├── deploy/      # Railway deployment guide
└── db/          # SQLite database (runtime; the Railway volume in production)
```

## License

See [LICENSE](LICENSE).

## Credits

Started from the FinAlly course project by Ed Donner (MIT licence); redesigned and extended by Paul Orlando.
