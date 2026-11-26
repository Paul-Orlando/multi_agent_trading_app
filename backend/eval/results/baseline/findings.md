## Findings

### Coverage and measurement conditions

- **Coverage: 24 of 117 calls answered (21%).** That's below the 95% bar, so the pass rate is indicative, not a full baseline. 24 of the 39 applicable questions (Q1–Q24 and Q31) have one answered run each. Q32–Q46 have none. Every unanswered call is a provider error, not a model failure.
- **Reply cap.** The run used an eval-only 4,000-token reply cap (`EVAL_MAX_TOKENS`), and every answered call was served by **Cerebras**. The live app as of this commit sends no cap and allows fallbacks, so visitors may get the uncapped behaviour in `../baseline-uncapped/` instead.
- **OpenRouter cut-offs.** OpenRouter refused calls with a 402 after about 25 in a row. A later audit captured the full error body: "You requested up to 117,484 tokens, but can only afford 6,731". OpenRouter reserves credit for the longest possible reply, and the remaining balance only covered a few thousand tokens. See `../../SCORING_CHANGES.md`.

### Capped results (Cerebras), 24 answered

- **Pass rate: 22 of 24.** The model saw the full portfolio context (1,104 input tokens on average) and answered in 0.39 s on average.
- **Trade intent: 7/7.** It read the requested trades correctly, including "$200 of AMZN" (1.081 shares), "half my NVDA" (2.5) and "all my Apple" (10).
- **No trade: 8/8.** It requested no trades and no watchlist changes.
- **Grounding: 6/8.** The answers were exact: $10,350.00, $550.00, NVDA +$200.00 (+5.3%), +$350.00 and AAPL $190.00.
- **Q23 failed** because of the app's data, not the model. Asked "Which position is doing worst?", it said AAPL (+$50, +2.7%), which is what the app's context says. The Analyzer ranks by dollar P&L. The plan expects JPM, the worst by percentage (+2.6%).
- **Q24 failed** on an unsupported figure. It said NVDA and JPM "together represent about 77%", which is correct arithmetic, but no 77% appears in the data the model was given.
- **Risk:** Q31 answered correctly: $750 needed against $550 of cash.
- **Unsupported figures: 12, in 5 replies.**
  - Most are correct arithmetic on numbers the app doesn't supply: position values ($4,000, $3,900), combined weight (77%), the 3-TSLA cost ($750) and a what-if portfolio after selling JPM.
  - One is wrong: Q10 calls AAPL "~5% of portfolio", but it's 18.4%; 5.3% is the cash share.
  - The plan's fix is to supply values and weights from the Analyzer and tell the model not to compute.

### Uncapped route, the labelled sample in `../baseline-uncapped/` (partial, 30 of 117 answered, fallback provider)

- **The model doesn't see the portfolio.** Input was about 361 tokens, so the second system message (the portfolio context) was dropped on the fallback route. The merged-message test confirmed this: 368 tokens with two messages, 646 with one. The model invented figures: total "$10,450", cash "$58,300", "120.5 shares of AAPL", "I don't have your portfolio details".
- **Junk trades.** 23 of 30 replies requested trades with tickers like `""`, `THE SIGHT`, `VOLUME` and `NP???`, and quantities of 0, -9, 7,070, 111,111 and 2,032,035. Risk rejected all of them.
- **Runaway replies.** There were eight replies over 1,000 tokens, up to 6,946 tokens and 59 s. OpenRouter showed 50–125 tokens/s, against about 200–230 on Cerebras.
- **Unrequested watchlist changes.** All 28 answered non-watchlist questions also requested watchlist changes, and six changed it: junk tickers `I`, `THE` and `RCDR` added, NVDA removed twice, and `ZZZZ` added.
- **Wrong quantities.** "$200 of AMZN" became 200 shares.

### Other findings

- **"Buy 1 ZZZZZ" fills** (uncapped sample, Q35). Risk approved it because the simulator invents a price for any ticker. It filled at **$172.40**, cash went from $550.00 to $377.60, and junk ticker `ZZZZ` was added to the watchlist. The mock run shows the same.
- **Q23's expected answer doesn't match the app's data.** See above. Fixing the Analyzer to rank by percentage, and to give both figures, is part of step 3a.
