"""Write the per-run CSV and the Markdown summary."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from .pricing import cost_usd

GROUP_TITLES = {
    "trade_intent": "Trade intent",
    "no_trade": "No trade",
    "grounding": "Grounding",
    "orders_alerts": "Orders & alerts",
    "risk": "Risk",
    "watchlist": "Watchlist",
    "refusals": "Refusals",
    "support_agent": "Support agent",
    "analytics": "Analytics",
    "market_events": "Market events",
}

CSV_FIELDS = [
    "label", "model", "question_id", "group", "run", "status", "reasons", "message",
    "requested_trades", "fills", "watchlist_after", "unsupported_count", "unsupported_figures",
    "latency_ms", "prompt_tokens", "completion_tokens", "cost_usd", "llm_error", "reply",
]


def p95(values: list[float]) -> float:
    """95th percentile, nearest-rank method."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _trades(ts: list[dict]) -> str:
    return "; ".join(f"{t['side']} {float(t['quantity']):g} {t['ticker']}" for t in ts)


def write_csv(path: Path, label: str, records: list[dict], price: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in records:
            cost = cost_usd(r["prompt_tokens"], r["completion_tokens"], price)
            w.writerow({
                "label": label,
                "model": r["model"],
                "question_id": r["question_id"],
                "group": r["group"],
                "run": r["run"],
                "status": status(r),
                "reasons": " | ".join(r["reasons"]),
                "message": r["message"],
                "requested_trades": _trades(r["requested_trades"]),
                "fills": _trades(r["fills"]),
                "watchlist_after": " ".join(r["watchlist_after"]),
                "unsupported_count": len(r["unsupported"]),
                "unsupported_figures": " ".join(r["unsupported"]),
                "latency_ms": r["latency_ms"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "cost_usd": "" if cost is None else f"{cost:.6f}",
                "llm_error": r["llm_error"] or "",
                "reply": r["reply"],
            })


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d:.0%})" if d else "0/0"


def _quote(text: str) -> str:
    return "\n".join("> " + line for line in (text or "(empty)").splitlines()) or "> (empty)"


# Answered calls must reach this share for a run to count as a valid measurement.
VALID_ANSWER_RATE = 0.95


def status(r: dict) -> str:
    """'error' = the provider never answered (not a model failure); otherwise 'pass' or 'fail'."""
    if r.get("llm_error"):
        return "error"
    return "pass" if r["passed"] else "fail"


def _yes_missing(by_q: dict[int, list[dict]]) -> str:
    missing = [q for q, rs in sorted(by_q.items()) if all(status(r) == "error" for r in rs)]
    return "yes" if not missing else "no, unanswered: " + ", ".join(f"Q{q}" for q in missing)


def write_summary(
    path: Path, meta: dict, records: list[dict], questions: dict[int, dict], skipped: list[dict]
) -> str:
    price = meta["price"]
    by_q: dict[int, list[dict]] = defaultdict(list)
    for r in records:
        by_q[r["question_id"]].append(r)
    answered = [r for r in records if status(r) != "error"]
    errored = [r for r in records if status(r) == "error"]
    runs_passed = sum(status(r) == "pass" for r in answered)

    def passed_every_run(rs: list[dict]) -> bool:
        ans = [r for r in rs if status(r) != "error"]
        return bool(ans) and all(status(r) == "pass" for r in ans)

    q_all = [q for q, rs in by_q.items() if passed_every_run(rs)]
    latencies = [r["latency_ms"] for r in answered]
    prompt_t = sum(r["prompt_tokens"] for r in records)
    completion_t = sum(r["completion_tokens"] for r in records)
    cost = cost_usd(prompt_t, completion_t, price)
    unsupported = sum(len(r["unsupported"]) for r in answered)
    replies_with = sum(1 for r in answered if r["unsupported"])
    rate = len(answered) / len(records) if records else 0.0
    valid = rate >= VALID_ANSWER_RATE

    lines = [
        f"# Evaluation: {meta['label']}",
        "",
        f"Model `{meta['model']}` · {meta['runs']} run(s) per question · {meta['started']}"
        + (" · mock LLM" if meta.get("mock") else "")
        + (f" · eval reply cap {meta['max_tokens']} tokens" if meta.get("max_tokens") else " · no reply cap"),
        "",
        "| Measure | Result |",
        "| --- | --- |",
        f"| Calls answered | {_pct(len(answered), len(records))}"
        f" — {'valid' if valid else 'NOT VALID'} (needs {VALID_ANSWER_RATE:.0%}) |",
        f"| Every question answered at least once | {_yes_missing(by_q)} |",
        f"| Runs passed (of answered) | {_pct(runs_passed, len(answered))} |",
        f"| Questions passed on every answered run | {_pct(len(q_all), len(by_q))} |",
        f"| Unsupported figures (total) | {unsupported} in {replies_with} of {len(answered)} replies |",
        f"| Provider errors (not graded) | {len(errored)} |",
        f"| Reply time, average | {sum(latencies) / len(latencies) / 1000 if latencies else 0:.2f} s |",
        f"| Reply time, 95th percentile | {p95(latencies) / 1000:.2f} s |",
        f"| Tokens (input / output) | {prompt_t:,} / {completion_t:,} |",
        "| Estimated cost | "
        + (f"${cost:.4f}" if cost is not None else "unknown")
        + (
            f" (OpenRouter list price, {price['provider']}: ${price['input_per_m']:.2f} in /"
            f" ${price['output_per_m']:.2f} out per million tokens)"
            if price.get("input_per_m") is not None
            else f" ({price.get('source', '')})"
        )
        + " |",
        f"| Questions not yet built (skipped) | {len(skipped)} |",
    ]
    for t in meta.get("retries", []):
        lines.append(
            f"| Retry of provider errors, {t['at']} | {t['recovered']} of {t['retried']} recovered"
            f" ({t['delay_s']:g}s between calls) |"
        )
    lines += [
        "",
        "## Results by group",
        "",
        "| Group | Questions | Runs passed (of answered) | Passed every answered run | Errors |",
        "| --- | --- | --- | --- | --- |",
    ]
    groups: dict[str, list[int]] = defaultdict(list)
    for qid in sorted(by_q):
        groups[questions[qid]["group"]].append(qid)
    for g in GROUP_TITLES:
        if g not in groups:
            continue
        rs = [r for q in groups[g] for r in by_q[q]]
        ans = [r for r in rs if status(r) != "error"]
        allq = sum(1 for q in groups[g] if passed_every_run(by_q[q]))
        lines.append(
            f"| {GROUP_TITLES[g]} | {len(groups[g])}"
            f" | {_pct(sum(status(r) == 'pass' for r in ans), len(ans))}"
            f" | {_pct(allq, len(groups[g]))} | {len(rs) - len(ans)} |"
        )

    providers: dict[str, list[dict]] = defaultdict(list)
    for r in answered:
        providers[r.get("provider") or "not recorded"].append(r)
    lines += ["", "## Serving provider", "",
              "| Provider | Answered calls | Avg input tokens | Avg output tokens | Runs passed |",
              "| --- | --- | --- | --- | --- |"]
    for name, rs in sorted(providers.items(), key=lambda kv: -len(kv[1])):
        lines.append(
            f"| {name} | {len(rs)} | {sum(r['prompt_tokens'] for r in rs) / len(rs):.0f}"
            f" | {sum(r['completion_tokens'] for r in rs) / len(rs):.0f}"
            f" | {_pct(sum(status(r) == 'pass' for r in rs), len(rs))} |"
        )

    lines += ["", "## Results by question", "",
              "| # | Group | Question | Passed (of answered) | Errors | Unsupported figures |",
              "| --- | --- | --- | --- | --- | --- |"]
    for qid in sorted(by_q):
        rs = by_q[qid]
        ans = [r for r in rs if status(r) != "error"]
        q = questions[qid]
        lines.append(
            f"| {qid} | {GROUP_TITLES[q['group']]} | {q['message']}"
            f" | {sum(status(r) == 'pass' for r in ans)}/{len(ans)} | {len(rs) - len(ans)}"
            f" | {sum(len(r['unsupported']) for r in ans)} |"
        )

    lines += ["", "## Not yet built", ""]
    if skipped:
        lines += ["| # | Group | Question | Needs |", "| --- | --- | --- | --- |"]
        lines += [
            f"| {q['id']} | {GROUP_TITLES[q['group']]} | {q['message']} | {q['requires']} |" for q in skipped
        ]
    else:
        lines.append("None.")

    # Hand-written findings live next to the results so --rescore keeps them.
    findings = path.parent / "findings.md"
    if findings.is_file():
        lines += ["", findings.read_text(encoding="utf-8").strip()]

    lines += ["", f"## Provider errors ({len(errored)})", ""]
    if errored:
        lines += ["| # | Run | Error |", "| --- | --- | --- |"]
        lines += [
            f"| {r['question_id']} | {r['run']} | {r['llm_error'].replace('|', '/')[:300]} |"
            for r in sorted(errored, key=lambda r: (r["question_id"], r["run"]))
        ]
    else:
        lines.append("None.")

    failures = [r for r in answered if status(r) == "fail"]
    lines += ["", f"## Failures ({len(failures)})", ""]
    for r in sorted(failures, key=lambda r: (r["question_id"], r["run"])):
        q = questions[r["question_id"]]
        lines += [
            f"### Q{r['question_id']} run {r['run']}: {q['message']}",
            "",
            f"Expected: {q['expected']}",
            "",
            "Why it failed: " + "; ".join(r["reasons"]),
            "",
            f"Requested trades: {_trades(r['requested_trades']) or 'none'} · Filled: {_trades(r['fills']) or 'none'}",
            "",
            "Reply:",
            "",
            _quote(r["reply"]),
            "",
        ]
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def save_runs(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            raw = {k: v for k, v in r.items() if k not in ("passed", "reasons")}
            f.write(json.dumps(raw, ensure_ascii=False) + "\n")


def load_runs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
