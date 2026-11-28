# FinAlly

A demo-only AI trading workstation: simulated prices, virtual money and a fictional company — not a real trading or advice service.
Stack: FastAPI backend in `backend/`, Next.js static-export frontend in `frontend/`, SQLite, LiteLLM via OpenRouter. Retired and no longer deployed.

The redesign plan is in `docs/REDESIGN_PLAN.md`. Earlier planning docs (the original FinAlly plan and market data design) are in `docs/history/` — consult them only when needed. Backend developer notes are in `backend/CLAUDE.md`.

## Never weaken these

Each rule applies as soon as the feature it covers is built. Never remove, bypass or loosen one to make a change easier.

- **Demo only.** Simulated prices, virtual money, fictional company and people, no real accounts, brokers or orders, and no investment advice. Never add anything that presents the app as a real trading or advice service.
- **Visitor isolation.** Every database query filters by the visitor's `user_id`.
- **AI trades need approval.** Trades proposed by the AI are order cards the visitor must approve, unless auto-execute is on and the order is within its caps.
- **Risk checks.** The Risk agent validates every trade.
- **Demo labelling.** The demo notice and the SIM label stay on by default.
- **Usage limits.** Usage limits are counted on the server and are never switched off on the live site.
- **AI errors.** AI error details are logged, never shown to visitors.

## The AI call

- Model `openai/gpt-oss-120b` on OpenRouter, served only by Cerebras: no fallbacks, `require_parameters` on. It uses one system message (the rules plus the live portfolio context), a reply cap (1500 tokens) and a 30-second timeout, with no automatic retries except one for malformed JSON. Settings: `OPENROUTER_MODEL`, `OPENROUTER_PROVIDER`, `OPENROUTER_MAX_TOKENS`, `OPENROUTER_TIMEOUT` (see `backend/app/agents/orchestrator.py`).
- Any change to the AI call, model, provider or prompt needs an evaluation run (`backend/eval/README.md`), compared with the last results in `backend/eval/results/`.

## Before saying a change is done

Run both, and make sure both pass:

```bash
cd backend && uv run --extra dev python -m pytest -q
cd frontend && npm run typecheck && npm run build
```

Never delete or loosen a test to make a change pass.

## Secrets

Never read, print or commit `.env` or any API key. Put placeholders in `.env.example`.

## Fictional details

The company, people, addresses and phone numbers are fictional. Phone numbers use the 555-01xx range and emails end in `.example`. Don't add real contact details.

## Commits

- Author: `Paul-Orlando` with the GitHub no-reply email (`283247483+Paul-Orlando@users.noreply.github.com`).
- No `Co-Authored-By`, session or AI-attribution lines in commit messages.
