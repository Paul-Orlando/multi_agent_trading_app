## About this run

**The uncapped route: the step 2 app code with no reply cap and fallbacks allowed, as the live app called the AI before step 3a.** It's a mixed run, with the serving provider shown per call:

- **30 calls on a fallback provider.** These were answered first, on 2026-11-26, while the OpenRouter account balance was **-$0.19**. OpenRouter couldn't reserve the uncapped maximum on Cerebras, so it routed elsewhere. The provider wasn't recorded at the time; OpenRouter's Activity page showed 50–125 tokens/s.
- **87 calls on Cerebras.** These were re-run on the same step 2 code (commit `04b3629`) after the balance was topped up, and all were served by Cerebras.

| Route | Calls | Avg input tokens | Avg output tokens | Passed |
| --- | --- | --- | --- | --- |
| Fallback (low balance) | 30 | 365 | 1,376 | 5/30 (17%) |
| Cerebras | 87 | 1,102 | 94 | 73/87 (84%) |

## Findings on the fallback route (the first 30 calls)

- **The model never saw the portfolio.** Input was a median of 361 tokens, so the second system message (the portfolio context) was dropped. It invented figures:
  - "Your current total portfolio value is $10,450.00" (Q17)
  - "Your portfolio currently holds $58,300 in cash" (Q18)
  - "Your portfolio's largest holding is 120.5 shares of AAPL" (Q19)
  - "I don't have your portfolio details visible" (Q20)
- **Junk trades.** 23 of 30 replies requested trades nobody asked for:
  - tickers such as `""`, `THE SIGHT`, `VOLUME`, `NP???`, `IT...` and `A0 ???`
  - quantities of 0, -1, -9, 7,070, 111,111 and 2,032,035

  Risk rejected every invalid one.
- **Runaway replies.** Eight replies ran over 1,000 tokens: Q21 6,946; Q32 6,132; Q17 5,822; Q6 5,617; Q12 3,381; Q37 3,197; Q4 2,525; Q15 2,051. The slowest took 59 s.
- **Unrequested watchlist changes.** All 28 answered non-watchlist questions also requested watchlist changes, and six actually changed it:
  - junk tickers `I`, `THE` and `RCDR` were added (Q2, Q17, Q21)
  - NVDA was removed (Q7, Q20)
  - `ZZZZ` was added (Q35)
- **Wrong quantities.** "Get me $200 of AMZN" became **200 shares** (Q3).
- **"Buy 1 ZZZZZ" filled** at an invented **$172.40**, taking cash from $550.00 to $377.60, and junk ticker `ZZZZ` was added to the watchlist.

## What fixed it

Step 3a removes this route:
- Cerebras only, with no fallbacks
- one system message
- a reply cap

A low balance now gives "The AI is unavailable right now; nothing was traded" instead of a wrong answer.
