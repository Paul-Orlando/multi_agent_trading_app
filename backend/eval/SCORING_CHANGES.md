# Scoring changes

Every change to how answers are graded (a question's `check` in `questions.json`, `grader.py`, or the fixture) is logged here with the date, what changed, why, and which results it affects. Re-grade saved runs with `--rescore` so earlier results stay comparable.

| Date | Change | Why | Affects |
| --- | --- | --- | --- |
| 2026-11-26 | `eval/grader.py`: curly quotes in the reply (’ ‘ “ ”) are turned into plain ones before the reply patterns are checked. | Grader bug: the model writes "can’t", and the patterns only matched "can't". So replies like "I can’t guarantee any stock’s price movement" (Q46) and "I can’t help with recommendations for real-world brokers" (Q42) failed although they meet the plan. | Re-graded with `--rescore`: baseline, baseline-uncapped, after-ai-call-fix, mock. |
| 2026-11-26 | Q35 check: added the phrasing "don't / doesn't have a price" to the accepted ways of saying the ticker isn't available. | "I don’t have a price for ZZZZZ, so I can’t place that trade" says the ticker isn't available, but no pattern covered it. Nothing filled. | Same re-grade. |
| 2026-11-26 | `eval/runner.py`: the recorded "context" (used for unsupported figures) is now every message the model gets with the static rules text removed, instead of every message after the first. | Since step 3a the rules and the portfolio context share one system message. The old rule would have dropped the portfolio data and counted every figure as unsupported. For runs made before step 3a, the result is the same. | `after-ai-call-fix` onwards. No change to earlier results. |

## Notes

These notes record what the evaluation found about the app, the provider and the measurement conditions. They aren't changes to scoring.

- **2026-11-26: the 402 cut-offs were caused by an exhausted account balance.** The OpenRouter account balance was **-$0.19**. It was topped up to $9.81 on 2026-11-26, and every call that had ended in a 402 was then re-run with `--retry-errors`. All of them were answered: baseline 93 of 93, baseline-uncapped 87 of 87, after-ai-call-fix 92 of 92.
  - **Not the code, not the key limit.** The key had used about $0.05 of its $5 limit.
  - **What the recording proxy captured** while the balance was negative:
    - **Uncapped requests:** "This request requires more credits, or fewer max_tokens. You requested up to 117,484 tokens, but can only afford 6,731" (`limit_source: openrouter_credits`).
    - **Capped requests:** `402 in_flight_budget_exhausted` with `Retry-After: 120`.
  - **How the old AI call made it worse.** It sent no reply cap, so OpenRouter reserved credit for the model's maximum reply. It also allowed fallbacks, so OpenRouter tried about 17 other providers.
  - **Requests per question:** one HTTP request each, with no hidden retries.
- **2026-11-26: on the fallback route the portfolio context is dropped.** Before step 3a, the orchestrator sent two system messages: the rules, then the live portfolio context. A local capture confirmed the app sent both.
  - **Who served the 30 calls:** the first 30 answered calls in `results/baseline-uncapped/` were made while the balance was low. OpenRouter routed them to a provider other than Cerebras (not recorded at the time; OpenRouter's Activity page showed 50–125 tokens/s). That provider dropped the second message: about 360 input tokens, against about 1,100 on Cerebras.
  - **Merged-message test on that route:** 368 tokens with two messages, 646 with one. With two messages the model invented "$152,340.20 total, $12,450.00 cash"; merged, it answered "$10,350.00, $550.00".
  - **Cerebras keeps both messages.** An earlier version of this note blamed Cerebras; that was wrong.
  - **After the top-up**, the same uncapped requests were served by Cerebras (87 of 87). So the fallback happened because Cerebras couldn't be afforded at the uncapped reservation.
  - **Step 3a removes the risk.** It sends one system message, allows no fallbacks and caps replies, so a low balance now gives "The AI is unavailable right now; nothing was traded" instead of a wrong answer.
- **2026-11-26: measurement conditions.**
  - **`baseline`:** the step 2 app code with an eval-only 4,000-token reply cap (`EVAL_MAX_TOKENS`). Every call was served by Cerebras. The 93 calls that had ended in 402s were re-run on the same step 2 code, checked out at commit `04b3629`, after the top-up.
  - **`baseline-uncapped`:** the step 2 code with no cap, as the live app called the AI before step 3a. It's a mixed run: 30 calls on the fallback route during the low balance, and 87 on Cerebras after the top-up. The serving provider is shown per call.
  - **`after-ai-call-fix`:** the step 3a code, using the app's own settings with no eval cap.
