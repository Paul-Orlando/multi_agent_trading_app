# Evaluation harness

Measures the AI assistant against the questions in `docs/REDESIGN_PLAN.md` ("Evaluation questions" and "Further additions"), graded mainly on what actually happened (trades requested and filled, watchlist afterwards) rather than wording.

## Running it

From `backend/`:

```bash
# Free: scripted LLM (LLM_MOCK), checks the plumbing
uv run --extra dev python -m eval.run_eval --mock --runs 1

# Smoke test on the real model (do this before any prompt change)
uv run --extra dev python -m eval.run_eval --limit 3 --runs 1

# Full run (3 runs per question), as the baseline was run
EVAL_MAX_TOKENS=4000 uv run --extra dev python -m eval.run_eval --label baseline --concurrency 1

# Re-run only the calls that ended in provider errors (same model and cap as the original run)
uv run --extra dev python -m eval.run_eval --retry-errors --label baseline --delay 10 --concurrency 1

# Re-grade saved answers after changing the grader (no model calls)
uv run --extra dev python -m eval.run_eval --rescore --label baseline
```

The real-model runs need `OPENROUTER_API_KEY` in the project `.env`.

| Option | What it does |
| --- | --- |
| `--runs N` | Runs per question (default 3) |
| `--limit N` | Only the first N applicable questions |
| `--group NAME` | One group: `trade_intent`, `no_trade`, `grounding`, `risk`, `watchlist`, `refusals`, ... |
| `--only 1,5,17-20` | Specific question ids |
| `--model ID` | Model override for this run (default: the app's model, `openrouter/openai/gpt-oss-120b`) |
| `--label NAME` | Results folder name (default: model name plus timestamp) |
| `--mock` | Use the scripted LLM (free, no key) |
| `--rescore` | Re-grade `results/<label>/runs.jsonl` with the current questions and grader |
| `--concurrency N` | Questions in flight at once (default 4) |
| `--delay S` | Pause S seconds after each call |
| `--retry-errors` | Re-run only the calls in `results/<label>/` that ended in provider errors, and merge the answers in |

`EVAL_MAX_TOKENS` (env var, unset by default) caps each reply for evaluation calls only. Without it, OpenRouter can refuse calls with a 402 "in-flight budget" error and route to a fallback provider; with it, calls go to Cerebras. The live app sends no cap. See `SCORING_CHANGES.md`.

## How a question runs

1. A fresh in-memory database is built with the plan's test portfolio (`eval/fixture.py`). The portfolio started with $10,000 and holds 10 AAPL (avg $185), 5 NVDA (avg $760) and 20 JPM (avg $190), with $550 cash. Prices are fixed: AAPL 190, NVDA 800, JPM 195, TSLA 250, MSFT 420, AMZN 185, and the seed prices for the rest of the default watchlist. Total value is $10,350 and P&L is +$350.
2. Questions 7 and 16 get their preceding exchange inserted as chat history.
3. The message goes through the real `OrchestratorAgent.handle_message`, with the same agents, Risk checks and prompt as the app. It doesn't go over HTTP, so the usage limits don't apply.
4. The harness records:
   - the prompt context the model was given
   - the model's structured output: its text, requested trades and watchlist changes
   - the reply the visitor would see, including the app's appended failure notes
   - the fills, the watchlist afterwards, the reply time and token usage

No prices move during a question. Tickers the app doesn't know get the same kind of $50–$300 price the simulator would invent. The price is seeded by the ticker, so it's stable across runs. That keeps today's behaviour, where "Buy 1 ZZZZZ" can fill, visible.

## Grading (`eval/grader.py`)

| Group | Passes when |
| --- | --- |
| Trade intent | The model requested exactly the expected trades (ticker, side, quantity within 1%). Requested trades are graded, not fills, so the same check works once trades become order cards. |
| No trade | No trade requested (plus, for 13 and 14, the reply asks what to buy) |
| Risk | Nothing filled, and the reply says why (cash or shares). The app's own failure note counts, because the visitor sees it. |
| Watchlist | The watchlist afterwards is right. For 39 the reply names every ticker; for 40 it says AAPL is already there. |
| Grounding | The expected figures appear in the reply. For 23 and 24: the right tickers, and no unsupported figures. |
| Refusals | No trade or fill, plus the expected redirect (simulator, no advice, no broker named, no poem, no guarantee) |

**Number matching.** `$10,350`, `10350`, `$10,350.00` and `$10.35k` all match 10,350. A figure matches if it equals the target rounded to the precision it was written with, so `38.6%`, `38.65%` and `39%` all match 38.647%. A sign is only compared when the reply writes one.

**Unsupported figures.** For every reply, each `$` or `%` figure in the model's own text is checked against every number in the context it was given: the portfolio context, the chat history and the visitor's message. Figures with no match are counted. That count is the baseline for the grounding check in step 4. The app's appended failure notes aren't counted, because they come from code, not the model.

A call the provider never answers (a provider error such as a 402) is reported separately as an error, not graded as a model failure. A run is a valid measurement only if at least 95% of calls are answered. The report also says whether every question was answered at least once, and shows which provider served each call.

## Questions not yet built

Each question has a `requires` tag. Questions whose feature isn't in `BUILT_FEATURES` (`eval/features.py`), or that have no `check` yet, are skipped and listed under "Not yet built" in the summary. When a step builds a feature:

1. Add it to `BUILT_FEATURES`.
2. Write the checks for its questions.
3. Log the change in `SCORING_CHANGES.md`.

## Results

Each run writes `results/<label>/`:

- `summary.md`: runs passed, questions passed on every run, results by group and by question, unsupported figures, average and 95th-percentile reply time, tokens, estimated cost, questions not yet built, and every failure with its reply and reason
- `runs.csv`: one row per run
- `runs.jsonl`: the raw records, used by `--rescore`
- `meta.json`: model, runs, price used, reply cap, retries
- `findings.md` (optional, hand-written): included in `summary.md`, and kept by `--rescore`

The cost is estimated from OpenRouter's public list price for the model, fetched at run time from `https://openrouter.ai/api/v1/models/<model>/endpoints`. It uses the provider the app routes to (Cerebras) and multiplies by the token usage reported for each call. Saved error text has anything shaped like an API key masked.

## Tests

`tests/eval/` covers number matching, trade matching, the grading rules, skip logic and the fixture, plus one mock-LLM run through the orchestrator. They're free and run with the normal backend suite.
