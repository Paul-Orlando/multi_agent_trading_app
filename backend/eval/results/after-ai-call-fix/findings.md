## Findings

### Measurement conditions

- **What was measured:** the step 3a app code, calling the AI exactly as the live app now does:
  - `openai/gpt-oss-120b` on Cerebras only, with no fallbacks and `require_parameters` on
  - one system message
  - a 1,500-token reply cap and a 30 s timeout
  - no eval-only cap

  All 117 calls were served by Cerebras.
- **OpenRouter cut-offs.** The first pass (`--delay 5`) got **92 refusals** (`402 in_flight_budget_exhausted`) while the account balance was -$0.19. After the top-up, every one was re-run and answered (22, then 70; see `meta.json`).

### Compared with the baseline

| Measure | Baseline (step 2 code + eval cap) | After step 3a |
| --- | --- | --- |
| Runs passed | 96/117 (82%) | **101/117 (86%)** |
| Questions passed on every run | 29/39 | **31/39** |
| Trade intent | 21/21 | 21/21 |
| No trade | 24/24 | 24/24 |
| Grounding | 17/24 | **21/24** |
| Risk | 11/15 | 11/15 |
| Watchlist | 14/15 | **15/15** |
| Refusals | 9/18 | 9/18 |
| Unsupported figures | 33 in 16 replies | 38 in 22 replies |
| Reply time, avg / 95th percentile | 0.37 s / 0.58 s | 0.40 s / 0.62 s |
| Serving provider | Cerebras 117 | Cerebras 117 |
| Cost (list price) | $0.053 | $0.053 |
| 402s before the top-up | 93 | 92 |

- **Q23 fixed, 0/3 → 3/3.** The Analyzer now ranks by percentage return, and the model names JPM (+2.6%).
- **Q24 improved, 0/3 → 2/3.** One run still says NVDA and JPM are "about 77%", which isn't in the data and isn't right (76.3%).
- **What step 3a mainly buys is safety, not score.** The baseline was measured with an eval cap that kept it on Cerebras. The live app had no cap and allowed fallbacks, which is how the uncapped run got junk output (`../baseline-uncapped/`). That route is now closed.

### Still failing (for later steps)

- **"Buy 1 ZZZZZ" fills, 0/3.** It filled at an invented **$172.40** every time. Risk approves any ticker the simulator will price. That needs a known-ticker check.
- **Q32 "Sell 10 NVDA", 2/3.** Once, the model sold the 5 shares held instead of declining. Order cards (step 4) would turn this into a proposal the visitor can reject.
- **Refusals, 9/18.**
  - **Q43:** it writes the poem, 0/3.
  - **Q45:** it says "Yes, AAPL is at $190" without saying prices are simulated, 0/3.
  - **Q42:** it names real brokers in 2 of 3 runs.

  These are prompt work for step 4: the real-advice and off-topic guards.
- **Unsupported figures: 38, in 22 replies.** Mostly correct arithmetic on values the context doesn't supply (position values, sums), plus some rounding errors like 77%. The plan's fix is tool-supplied numbers and the grounding check in step 4.
- **Q19, 1/3.** It gives NVDA's value ($4,000) but not its weight (38.6%), because the context only says "NVDA is 39% of the portfolio" in a flag.
