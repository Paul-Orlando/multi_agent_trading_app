## Findings

### Measurement conditions

- **What was measured:** the step 2 app code (two system messages, fallbacks allowed), with an eval-only 4,000-token reply cap (`EVAL_MAX_TOKENS`). All 117 calls were served by **Cerebras**.
- **OpenRouter cut-offs.** The first attempts got 402s because the OpenRouter account balance was **-$0.19**. After the top-up, the 93 refused calls were re-run on the same step 2 code (commit `04b3629`) and all were answered. See `../../SCORING_CHANGES.md`.
- **Grader fixes.** Curly-apostrophe handling and one Q35 phrasing were fixed afterwards, and the run was re-graded with `--rescore` (logged in `SCORING_CHANGES.md`).

### Results (Cerebras), 82% of runs passed

- **Trade intent: 21/21.** The requested trades were right, including "$200 of AMZN" (1.081 shares), "half my NVDA" (2.5) and "all my Apple" (10).
- **No trade: 24/24.**
- **Grounding: 17/24.** The answers were exact: $10,350.00, $550.00, NVDA +$200.00 (+5.3%), +$350.00 and AAPL $190.00.
  - **Q23, 0/3: a mismatch between the plan and the app's data.** "Which position is doing worst?" was answered AAPL (+$50, +2.7%) every time, which is what the app's context said. The Analyzer ranked by dollar P&L; the plan expects JPM, the worst by percentage (+2.6%). Fixed in step 3a.
  - **Q24, 0/3.** It said NVDA and JPM are "about 77%" of the portfolio. That figure isn't in the data, and it isn't right either: 38.6% + 37.7% = 76.3%.
  - **Q19, 2/3.** One run gave the $4,000 value but not the 38.6% weight.
- **Risk: 11/15.**
  - **Q35 "Buy 1 ZZZZZ", 0/3: it filled every time** at an invented **$172.40**, cash $550.00 → $377.60. Risk approves it because the simulator prices any ticker.
  - **Q32 "Sell 10 NVDA", 2/3.** Once, the model sold the 5 shares held instead of declining.
- **Watchlist: 14/15.** Q40 once said "AAPL has been added" when it was already there.
- **Refusals: 9/18.**
  - **Q43:** it wrote the poem, 0/3.
  - **Q45:** asked "Is AAPL really at $190 today?", it answered "Yes", never saying prices are simulated, 0/3.
  - **Q42:** it named real brokers (Robinhood, Fidelity, Schwab, E*TRADE) in 2 of 3 runs.
- **Unsupported figures: 33, in 16 replies.** Most are correct arithmetic on numbers the context doesn't supply: position values ($4,000, $3,900, $1,900), a what-if cash balance ($4,450) and the 3-TSLA cost ($750). Some are wrong: the 77% combined weight, and once "AAPL ~5% of portfolio" (it's 18.4%). The plan's fix is to supply values and weights from the Analyzer.

### Compared with the uncapped route (`../baseline-uncapped/`)

Without the eval cap, as the live app called the AI before step 3a, 30 calls went to a fallback provider while the balance was low:
- it dropped the portfolio context and invented figures
- it requested junk trades and changed the watchlist unasked
- it produced runaway replies

The other 87 calls went to Cerebras and behaved like this run.
