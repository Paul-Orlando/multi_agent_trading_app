# Deploying Copperline to Railway

Railway builds the repo with **Railpack**, configured by `railway.toml` (build and start commands,
health check) and `railpack.json` (Node 20 and Python 3.12). You get a public
`https://<name>.up.railway.app` link.

## How the build works

| Step | What runs |
|---|---|
| Tools | Railpack installs Node 20 and Python 3.12 (`railpack.json`) |
| Build | `python -m pip install uv`, then `uv sync --frozen --no-dev` in `backend/`, which downloads a self-contained Python 3.12 into `/app/.uv-python` and builds `backend/.venv` on it (Railpack ships only `/app`; its own Python under `/mise` isn't in the deployed image), and logs the interpreter path; `npm ci` and `npm run build` in `frontend/` (static export to `frontend/out`), copied to `/app/static`, where the backend serves it |
| Start | `.venv/bin/python -m uvicorn app.main:app` from `backend/` (after logging where the venv's interpreter points), on Railway's `$PORT`, with `FINALLY_DB_PATH=/app/db/finally.db` |
| Health check | Railway waits for `GET /api/health` to return 200 before routing traffic |

The code lives at `/app` in the deployed image, so the database file is `/app/db/finally.db`.

## Steps

1. **Connect the repo.** On railway.com: *New Project, Deploy from GitHub repo*, choose
   `Paul-Orlando/multi_agent_trading_app`. Railway finds `railway.toml` and starts a build.
2. **Check the builder.** In *Settings, Build*, the builder should show **Railpack**. `railway.toml`
   sets it, and settings in code override the dashboard.
3. **Add variables** (service *Variables* tab):

   | Variable | Value | Why |
   |---|---|---|
   | `OPENROUTER_API_KEY` | your `sk-or-...` key | AI chat |
   | `RATE_LIMIT_CHAT_PER_HOUR` | `15` (default) | optional; max `POST /api/chat` per IP per hour |
   | `RATE_LIMIT_TRADES_PER_HOUR` | `20` (default) | optional; max trades per IP per hour |
   | `LLM_MOCK` | `false` (or `true` to run without the model) | optional |
   | `MASSIVE_API_KEY` | optional | real market data instead of the simulator |

   Do **not** set `PORT`; Railway injects it. `FINALLY_DB_PATH` is set by the start command.
4. **Attach a volume for the database.** Service, *Settings, Volumes* (or Ctrl/Cmd+K, then
   "Volume"), *Add volume*, mount path **`/app/db`**. Without it the database is wiped on every
   deploy and restart.
5. **Generate the public link.** Service, *Settings, Networking, Public Networking, Generate
   Domain*.
6. **Check it.** Open `https://<your-domain>/api/health` (expect `{"status":"ok"}`), then the
   root URL for the app.

Changing a variable or attaching the volume triggers a redeploy; watch *Deployments, View logs*.

## Read this before sharing the link

- **There is no login.** Anyone with the URL can trade in your portfolio and use the AI chat,
  which **spends your OpenRouter credits**. Keep the link private, use the two protection layers
  below, or set `LLM_MOCK=true`. Basic-auth protection is a small addition if you want it.
- **Chat model:** `openai/gpt-oss-120b` through OpenRouter, pinned to the Cerebras provider.

## Abuse protection: two layers

1. **Layer 1, code (per IP, in memory).** The app answers `429 Too Many Requests` with a
   `Retry-After` header once an IP exceeds:
   - **15** `POST /api/chat` requests per hour (`RATE_LIMIT_CHAT_PER_HOUR`)
   - **20** trades per hour (`RATE_LIMIT_TRADES_PER_HOUR`), shared by `/api/trade` and
     `/api/portfolio/trade`

   Counters live in process memory: they reset on redeploy or restart, and they assume the single
   replica above. The IP is the last `X-Forwarded-For` entry (the one Railway's proxy added).
2. **Layer 2, provider (hard spend cap).** Code limits can be bypassed or misconfigured, so also
   cap the money itself. In the OpenRouter web UI: *Settings, Keys* (openrouter.ai/settings/keys),
   open the key used as `OPENROUTER_API_KEY`, set a **Credit limit**, and save. Use a dedicated key
   for this deployment. Once the limit is reached OpenRouter rejects requests, so chat fails
   ("AuthenticationError"/402-style errors) instead of running up a bill. Keep the account's
   credit balance small as well.

Layer 1 stops casual abuse and keeps normal use smooth; layer 2 bounds the worst case.
- **Run exactly one replica.** The database is a single SQLite file and prices come from an
  in-process simulator, so scaling out would give each copy its own state.
- **Simulated prices** are the default (no Massive key). Trading uses virtual money.
- Live prices use Server-Sent Events over one long-lived connection. That is expected to work
  through Railway's proxy, but confirm after the first deploy: the header dot should turn green.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "Application failed to respond" / 502 | The app is not on `$PORT`, or the health check failed; read the deploy logs |
| Build fails at `npm ci` or `uv sync` | A lockfile is out of date: run `npm install` in `frontend/` or `uv lock` in `backend/` and commit the lockfile |
| Build fails with "no provider" or a missing `python`/`node` | `railpack.json` is missing from the repo root, or the builder isn't Railpack |
| Logs show `cannot execute: required file not found`, or the start line says `exists: no` | The venv's interpreter isn't in the deployed image: it must be under `/app`. The build command has to keep `UV_PYTHON_INSTALL_DIR=/app/.uv-python UV_PYTHON_PREFERENCE=only-managed`. Compare the `venv python:` line in the build log with the start line |
| Logs show `unable to open database file` | The volume is not mounted at `/app/db` |
| Chat replies "AuthenticationError" | `OPENROUTER_API_KEY` is missing or invalid in Railway variables |
| Data resets after every deploy | The volume is not attached, or is mounted at a different path |
