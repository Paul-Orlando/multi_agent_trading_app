# Scoring changes

Every change to how answers are graded (a question's `check` in `questions.json`, `grader.py`, or the fixture) is logged here with the date, what changed, why, and which results it affects. Re-grade saved runs with `--rescore` so earlier results stay comparable.

| Date | Change | Why | Affects |
| --- | --- | --- | --- |

## Notes

These notes record what the evaluation found about the app, the provider and the measurement conditions. They aren't changes to scoring.

- **2026-11-26: the fallback provider drops the portfolio context.** The orchestrator sends two system messages: the rules, then the live portfolio context. A local capture of the request confirmed the app sends both.
  - **Uncapped calls:** the app sets no reply cap and allows provider fallbacks. These calls weren't served by Cerebras, according to the token counts and OpenRouter's Activity page. The fallback route dropped the second system message: about 360 input tokens, against about 1,100 on Cerebras.
  - **Merged test on that route:** the same text was billed as 368 tokens when sent as two messages and 646 when merged into one. With two messages the model invented "$152,340.20 total, $12,450.00 cash"; merged, it answered "$10,350.00, $550.00".
  - **Cerebras keeps both messages.** An earlier version of this note blamed Cerebras; that was wrong.
  - The uncapped route also produced junk trade entries and runaway replies, up to 6,946 tokens. See `results/baseline-uncapped/`.
- **2026-11-26: measurement condition, reply cap of 4000 tokens.** The baseline runs with `EVAL_MAX_TOKENS=4000`, an eval-only setting that is unset by default. With the cap, OpenRouter routes the calls to Cerebras, the provider the app asks for first, and the provider is recorded for every call.
  - **The live app sends no cap and allows fallbacks**, so live visitors may get the uncapped, fallback behaviour instead of what the baseline measures.
  - The app's AI call is fixed in step 3; that fix isn't part of this evaluation.
- **2026-11-26: OpenRouter cut-offs.** Even one call at a time, OpenRouter refused calls after about 25–30 in a row with `402 in_flight_budget_exhausted` ("would exceed your available credits given your current in-flight requests"), although the account had credit. After a pause, calls worked again.
  - The calls that failed were re-run with `--retry-errors --delay 10`.
  - Calls that never got an answer are reported as provider errors, not model failures, and each question needs at least one answered run.
