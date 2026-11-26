# FinAlly end-to-end tests

Playwright tests that drive the real app in a browser.

## Run

The suite needs the app running on port 8000 with `LLM_MOCK=true` (deterministic replies, no API
key or network) and a **fresh** database: step 1 checks for $10,000 and the default watchlist.

1. Build the frontend and start the backend with a throwaway database (from the project root, in one terminal):

   ```bash
   cd frontend && npm ci && npm run build && cd ..
   cd backend && uv sync
   LLM_MOCK=true FINALLY_DB_PATH=:memory: FINALLY_STATIC_DIR=../frontend/out uv run uvicorn app.main:app --port 8000
   ```

   PowerShell: `$env:LLM_MOCK="true"; $env:FINALLY_DB_PATH=":memory:"; $env:FINALLY_STATIC_DIR="../frontend/out"; uv run uvicorn app.main:app --port 8000`

2. Run the tests (in a second terminal):

   ```bash
   cd test && npm ci && npx playwright install chromium
   npx playwright test
   ```

The exit code is the test result (0 = all passed). Restart the backend before each run, so the
in-memory database starts fresh. To test another instance, set `BASE_URL`, e.g.
`BASE_URL=http://localhost:8000 npx playwright test`.

## When a test fails

Artifacts for failing tests only are written to `test/test-results/` (full-page screenshot,
Playwright trace, video) and the HTML report to `test/playwright-report/`:

```bash
cd test && npx playwright show-report      # or open a trace: npx playwright show-trace <trace.zip>
```

## Layout

```
test/
  e2e/
    test_full_workflow.spec.ts   the 10-step workflow (serial; each step builds on the last)
    helpers.ts                   parsing, placeTrade(), API cross-checks, flash recorder, severable proxy
    pages/                       page objects: Header, Watchlist, TradeForm, Positions, Chat, Heatmap, PnLChart
  playwright.config.ts
```

The workflow steps: fresh start, price streaming and flashes, manual buy, AI question, AI trade,
AI watchlist add, heatmap, sell, P&L chart, SSE reconnect.

## Notes for maintainers

- After upgrading `@playwright/test` in `package.json`, run `npx playwright install chromium` again.
- The price-flash classes last only 500ms, so step 2 counts them with a `MutationObserver` instead
  of polling for them.
- Step 10 cuts a real TCP connection through a small in-process proxy. Chromium's
  `context.setOffline()` does **not** close an already-open EventSource, so it can't test reconnects.
- Heatmap colours depend on live P&L, which is usually near zero right after buying. Step 7 asserts
  green/red only when the P&L is clearly positive/negative, and "muted neutral" otherwise.
