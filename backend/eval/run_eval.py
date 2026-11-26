"""Run the evaluation. From backend/:  uv run --extra dev python -m eval.run_eval --help"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from app.agents import orchestrator as orchestrator_module
from app.db import PROJECT_ROOT

from .features import is_applicable
from .grader import grade, unsupported_figures
from .pricing import fetch_price
from .report import load_runs, save_runs, write_csv, write_summary
from .runner import eval_max_tokens, install_usage_capture, run_question, set_model

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = EVAL_DIR / "questions.json"
RESULTS_DIR = EVAL_DIR / "results"


def load_questions() -> list[dict]:
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]


def parse_only(spec: str | None) -> set[int] | None:
    """'1,5,17-20' -> {1, 5, 17, 18, 19, 20}."""
    if not spec:
        return None
    ids: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            ids.update(range(int(a), int(b) + 1))
        elif part:
            ids.add(int(part))
    return ids


def select(questions: list[dict], args) -> tuple[list[dict], list[dict]]:
    """Questions to run, and the selected ones skipped because their feature isn't built yet."""
    only = parse_only(args.only)
    chosen = [
        q for q in questions
        if (only is None or q["id"] in only) and (not args.group or q["group"] == args.group)
    ]
    run = [q for q in chosen if is_applicable(q)]
    skipped = [q for q in chosen if not is_applicable(q)]
    if args.limit:
        run = run[: args.limit]
    return run, skipped


def grade_all(records: list[dict], questions: dict[int, dict]) -> None:
    for r in records:
        # Recomputed on rescore so a grader change applies to saved answers too.
        r["unsupported"] = unsupported_figures(r["model_message"], r["context"])
        r["passed"], r["reasons"] = grade(questions[r["question_id"]], r)


def write_reports(out: Path, meta: dict, records: list[dict], questions: dict, skipped: list[dict]) -> str:
    write_csv(out / "runs.csv", meta["label"], records, meta["price"])
    return write_summary(out / "summary.md", meta, records, questions, skipped)


async def run_pairs(pairs: list[tuple[dict, int]], concurrency: int, delay: float = 0.0) -> list[dict]:
    """Run (question, run number) pairs. `delay` pauses after each call inside its slot, so with
    concurrency 1 calls are spaced `delay` seconds apart."""
    sem = asyncio.Semaphore(concurrency)
    done = 0
    total = len(pairs)

    async def one(q: dict, run: int) -> dict:
        nonlocal done
        async with sem:
            rec = await run_question(q, run)
            done += 1
            status = "error" if rec["llm_error"] else f"{rec['latency_ms'] / 1000:.1f}s"
            print(f"  [{done}/{total}] Q{q['id']} run {run}: {status}", flush=True)
            if delay and done < total:
                await asyncio.sleep(delay)
        return rec

    records = await asyncio.gather(*(one(q, run) for q, run in pairs))
    return sorted(records, key=lambda r: (r["question_id"], r["run"]))


async def run_all(selected: list[dict], runs: int, concurrency: int, delay: float = 0.0) -> list[dict]:
    pairs = [(q, run) for run in range(1, runs + 1) for q in selected]
    return await run_pairs(pairs, concurrency, delay)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Evaluate the AI assistant against questions.json.")
    p.add_argument("--limit", type=int, help="run only the first N applicable questions")
    p.add_argument("--runs", type=int, default=3, help="runs per question (default 3)")
    p.add_argument("--group", help="only this group, e.g. grounding")
    p.add_argument("--only", help="question ids, e.g. '1,5,17-20'")
    p.add_argument("--model", help=f"model override (default {orchestrator_module.DEFAULT_MODEL})")
    p.add_argument("--label", help="results folder name under eval/results/")
    p.add_argument("--mock", action="store_true", help="use LLM_MOCK (free, no API key)")
    p.add_argument("--rescore", action="store_true",
                   help="re-grade the saved answers in results/<label>/ without calling the model")
    p.add_argument("--concurrency", type=int, default=4, help="questions in flight at once")
    p.add_argument("--delay", type=float, default=0.0, help="seconds to pause after each call")
    p.add_argument("--retry-errors", action="store_true",
                   help="re-run only the calls in results/<label>/ that ended in provider errors")
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy codepage

    questions = load_questions()
    by_id = {q["id"]: q for q in questions}

    if args.rescore:
        if not args.label:
            p.error("--rescore needs --label naming a saved results folder")
        out = RESULTS_DIR / args.label
        meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        records = load_runs(out / "runs.jsonl")
        grade_all(records, by_id)
        skipped = [by_id[i] for i in meta.get("skipped_ids", [])]
        meta["rescored"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        print(write_reports(out, meta, records, by_id, skipped))
        return 0

    # The key comes from the project .env (never printed). LLM_MOCK is set explicitly either way,
    # so a value left in .env cannot silently turn a real run into a mock one.
    load_dotenv(PROJECT_ROOT / ".env")
    os.environ["LLM_MOCK"] = "true" if args.mock else "false"
    if not args.mock and not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set (add it to .env, or use --mock).", file=sys.stderr)
        return 2

    if args.retry_errors:
        if not args.label:
            p.error("--retry-errors needs --label naming a saved results folder")
        return retry_errors(RESULTS_DIR / args.label, by_id, args)

    model = set_model(args.model)
    selected, skipped = select(questions, args)
    if not selected:
        print("No applicable questions selected.", file=sys.stderr)
        return 2

    started = datetime.now(UTC)
    label = args.label or (
        ("mock" if args.mock else model.rsplit("/", 1)[-1]) + started.strftime("-%Y%m%d-%H%M")
    )
    out = RESULTS_DIR / label
    out.mkdir(parents=True, exist_ok=True)

    if args.mock:
        price = {"provider": "mock", "input_per_m": 0.0, "output_per_m": 0.0, "source": "mock LLM"}
    else:
        install_usage_capture()
        price = fetch_price(model, orchestrator_module.LLMSettings.from_env().provider)

    cap = eval_max_tokens()
    print(f"Running {len(selected)} question(s) x {args.runs} run(s) on {model}"
          f"{' (mock)' if args.mock else ''}{f', reply cap {cap}' if cap and not args.mock else ''};"
          f" {len(skipped)} not yet built.")
    records = asyncio.run(run_all(selected, args.runs, args.concurrency, args.delay))

    meta = {
        "label": label,
        "model": model,
        "mock": args.mock,
        "runs": args.runs,
        "started": started.strftime("%Y-%m-%d %H:%M UTC"),
        "price": price,
        "max_tokens": None if args.mock else eval_max_tokens(),
        "question_ids": [q["id"] for q in selected],
        "skipped_ids": [q["id"] for q in skipped],
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    save_runs(out / "runs.jsonl", records)
    grade_all(records, by_id)
    print(write_reports(out, meta, records, by_id, skipped))
    print(f"Results in {out}")
    return 0


def retry_errors(out: Path, by_id: dict[int, dict], args) -> int:
    """Re-run the saved calls that ended in provider errors, with the original model and cap,
    and merge the new answers into the same results folder."""
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    records = load_runs(out / "runs.jsonl")
    failed = [r for r in records if r.get("llm_error")]
    if not failed:
        print("No provider errors to retry.")
        return 0
    if meta.get("mock"):
        os.environ["LLM_MOCK"] = "true"
    # Same measurement conditions as the original run.
    if meta.get("max_tokens"):
        os.environ["EVAL_MAX_TOKENS"] = str(meta["max_tokens"])
    else:
        os.environ.pop("EVAL_MAX_TOKENS", None)
    set_model(meta["model"])
    if not meta.get("mock"):
        install_usage_capture()

    print(f"Retrying {len(failed)} call(s) that ended in provider errors"
          f" (reply cap {meta.get('max_tokens') or 'none'}, delay {args.delay:g}s).")
    pairs = [(by_id[r["question_id"]], r["run"]) for r in failed]
    fresh = {(r["question_id"], r["run"]): r for r in asyncio.run(run_pairs(pairs, args.concurrency, args.delay))}
    records = [fresh.get((r["question_id"], r["run"]), r) for r in records]
    recovered = sum(1 for r in fresh.values() if not r["llm_error"])
    meta.setdefault("retries", []).append({
        "at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "retried": len(failed),
        "recovered": recovered,
        "delay_s": args.delay,
    })
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    save_runs(out / "runs.jsonl", records)
    grade_all(records, by_id)
    skipped = [by_id[i] for i in meta.get("skipped_ids", [])]
    write_reports(out, meta, records, by_id, skipped)
    left = sum(1 for r in records if r["llm_error"])
    print(f"Recovered {recovered} of {len(failed)}; {left} provider error(s) remain. Results in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
