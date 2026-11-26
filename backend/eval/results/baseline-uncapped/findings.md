## About this sample

**Partial: 30 of 117 calls answered, on the fallback-provider route.** This is not a valid baseline (the bar is 95% answered). It's kept as evidence of what the app gets when it calls the model as it does today: no reply cap, fallbacks allowed. The valid baseline is in `../baseline/` (Cerebras, eval reply cap 4000 tokens).

- **How it was run:** 2026-11-26, one call at a time, app unchanged. The first 30 calls were answered. From call 31 onwards OpenRouter refused every call with `402 in_flight_budget_exhausted` (listed below as provider errors).
- **Provider:** the harness didn't record the provider yet. The pattern on OpenRouter's Activity page and the token counts point to a provider other than Cerebras. Capped calls served by Cerebras use about 1,100 input tokens at about 200–230 tokens/s with short replies.
- **Input tokens:** median 361 (range 356–425). That's too few to include the portfolio context, so the second system message was dropped.
- **Output:** median 227 tokens and 3.0 s, but with runaway replies of up to 6,946 tokens and 59 s. Eight replies ran over 1,000 tokens: Q21 6,946; Q32 6,132; Q17 5,822; Q6 5,617; Q12 3,381; Q37 3,197; Q4 2,525; Q15 2,051. OpenRouter showed 50–125 tokens/s.

## Findings in this sample

- **The model never saw the portfolio.**
  - "Your current total portfolio value is $10,450.00" (Q17)
  - "Your portfolio currently holds $58,300 in cash" (Q18)
  - "Your portfolio's largest holding is 120.5 shares of AAPL" (Q19)
  - "I don't have your portfolio details visible" (Q20)
  - "I need to view your current portfolio holdings" (Q21)
- **Junk trades.** 23 of 30 replies requested trades nobody asked for:
  - tickers such as `""`, `THE SIGHT`, `VOLUME`, `NP???`, `IT...` and `A0 ???`
  - quantities of 0, -1, -9, 7,070, 111,111 and 2,032,035

  Risk rejected every invalid one, so none of them filled.
- **Unrequested watchlist changes.** 28 of the 28 answered non-watchlist questions also requested watchlist changes. Six of them actually changed the watchlist:
  - junk tickers `I`, `THE` and `RCDR` were added (Q2, Q17, Q21)
  - NVDA was removed (Q7, Q20)
  - `ZZZZ` was added (Q35)
- **Wrong quantities.** "Get me $200 of AMZN" became **200 shares** (Q3).
- **"Buy 1 ZZZZZ" filled.** The model requested it, Risk approved it because the simulator invents a price for any ticker, and it filled at **$172.40**. Cash went from $550.00 to $377.60, and a junk ticker `ZZZZ` was added to the watchlist.
