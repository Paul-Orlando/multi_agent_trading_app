"""Evaluation harness: number matching, trade matching, skip logic and the fixture. All free."""

import json

import pytest

from eval.features import ALL_FEATURES, is_applicable
from eval.fixture import build_fixture, price_for
from eval.grader import (
    extract_figures,
    figure_matches,
    grade,
    looks_like_poem,
    reply_has_figure,
    trades_match,
    unsupported_figures,
)
from eval.run_eval import QUESTIONS_PATH, load_questions, parse_only
from eval.runner import run_question

# ---------------------------------------------------------------- number matching


@pytest.mark.parametrize(
    "reply",
    ["Your total is $10,350.", "about $10,350.00 in total", "10350 dollars", "$10.35k", "≈$10.4K"],
)
def test_total_value_written_many_ways(reply):
    assert reply_has_figure(reply, 10350)


@pytest.mark.parametrize("reply", ["$10,530", "$1,035", "$10,349", "10.2k"])
def test_wrong_totals_do_not_match(reply):
    assert not reply_has_figure(reply, 10350)


@pytest.mark.parametrize("reply,ok", [("38.6%", True), ("38.65%", True), ("about 39%", True),
                                      ("38%", False), ("38.5%", False), ("40%", False)])
def test_rounding_allowed_to_the_precision_written(reply, ok):
    assert reply_has_figure(reply, 38.647) is ok


def test_sign_only_compared_when_written():
    assert reply_has_figure("You're up $200 on NVDA", 200)
    assert reply_has_figure("+$200", 200)
    assert not reply_has_figure("-$200", 200)
    assert not reply_has_figure("−$200", 200)


def test_figure_kinds():
    kinds = {f.raw: f.kind for f in extract_figures("Cash $550 is 5.3% of 10 shares")}
    assert kinds == {"$550": "dollar", "5.3%": "percent", "10": "plain"}


def test_numbers_inside_words_are_ignored():
    assert [f.value for f in extract_figures("gpt-oss-120b Q3 AAPL")] == []


def test_figure_matches_uses_the_coarser_precision():
    (fig,) = extract_figures("38.65%")
    assert figure_matches(fig, 38.6, target_step=0.1)  # context "38.6%" supports a reply "38.65%"
    assert not figure_matches(fig, 38.6)


def test_unsupported_figures_counts_only_dollars_and_percents_not_in_context():
    context = "Cash: $550.00\nTotal value: $10,350.00 (P&L $+350.00)\n  NVDA: 5 sh, P&L $+200.00 (+5.3%)"
    message = "You have $550 cash, NVDA is up 5.3% ($200), total $10,350; buying 3 TSLA costs $750 (7.2%)."
    assert unsupported_figures(message, context) == ["$750", "7.2%"]


# ---------------------------------------------------------------- trade matching


def trade(ticker, side, qty):
    return {"ticker": ticker, "side": side, "quantity": qty}


def test_trade_match_within_one_percent():
    assert trades_match([trade("AMZN", "buy", 1.08)], [trade("AMZN", "buy", 1.0811)])[0]
    assert not trades_match([trade("AMZN", "buy", 1.0)], [trade("AMZN", "buy", 1.0811)])[0]


def test_trade_match_is_order_independent_and_exact_in_count():
    want = [trade("MSFT", "buy", 1), trade("JPM", "sell", 2)]
    assert trades_match([trade("JPM", "sell", 2), trade("MSFT", "buy", 1)], want)[0]
    assert not trades_match([trade("MSFT", "buy", 1)], want)[0]
    assert not trades_match(want + [trade("AAPL", "buy", 1)], want)[0]


def test_trade_match_checks_side_and_ticker():
    assert not trades_match([trade("TSLA", "sell", 1)], [trade("TSLA", "buy", 1)])[0]
    assert not trades_match([trade("TSL", "buy", 1)], [trade("TSLA", "buy", 1)])[0]
    assert trades_match([trade("tsla", "buy", 1)], [trade("TSLA", "buy", 1)])[0]


# ---------------------------------------------------------------- grading rules


def record(**kw):
    base = {"reply": "", "model_message": "", "context": "", "requested_trades": [], "fills": [],
            "watchlist_after": ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"],
            "unsupported": [], "llm_error": None}
    base.update(kw)
    return base


def test_risk_question_needs_no_fill_and_a_reason():
    q = {"check": {"no_fill": True, "reply_any": ["cash"]}}
    assert grade(q, record(reply="Not enough cash for that."))[0]
    assert not grade(q, record(reply="Done!", fills=[trade("TSLA", "buy", 3)]))[0]
    assert not grade(q, record(reply="I can't do that."))[0]


def test_no_trade_fails_on_any_requested_trade():
    q = {"check": {"no_trade": True}}
    assert grade(q, record())[0]
    passed, reasons = grade(q, record(requested_trades=[trade("NVDA", "buy", 1)]))
    assert not passed and "buy 1 NVDA" in reasons[0]


def test_ai_error_is_a_failure():
    passed, reasons = grade({"check": {"no_trade": True}}, record(llm_error="RateLimitError"))
    assert not passed and "RateLimitError" in reasons[0]


def test_watchlist_checks():
    q = {"check": {"watchlist_includes": ["PYPL"], "watchlist_excludes": ["NFLX"]}}
    assert grade(q, record(watchlist_after=["AAPL", "PYPL"]))[0]
    assert not grade(q, record(watchlist_after=["AAPL", "NFLX"]))[0]


def test_poem_detection():
    poem = "Stocks rise high\nStocks fall low\nTickers flash by\nWhere will they go"
    assert looks_like_poem(poem)
    assert not looks_like_poem("I can't write poems, but I can help with your portfolio.")
    assert not looks_like_poem("- AAPL\n- NVDA\n- JPM\n- TSLA")


# ---------------------------------------------------------------- questions and skip logic


def test_all_63_questions_with_valid_fields():
    qs = load_questions()
    assert [q["id"] for q in qs] == list(range(1, 64))
    for q in qs:
        assert q["requires"] in ALL_FEATURES
        assert q["message"] and q["expected"] and q["group"]
    assert all(qs[i - 1]["preceding"] for i in (7, 16))
    json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))


def test_skip_logic():
    built = {"none"}
    assert is_applicable({"requires": "none", "check": {"no_trade": True}}, built)
    assert not is_applicable({"requires": "orders_alerts", "check": {"no_trade": True}}, built)
    assert not is_applicable({"requires": "none", "check": None}, built)
    assert is_applicable({"requires": "orders_alerts", "check": {}}, built | {"orders_alerts"})


def test_unbuilt_features_are_skipped_today():
    skipped = {q["id"] for q in load_questions() if not is_applicable(q)}
    assert skipped == {8, *range(25, 31), *range(47, 64)}


def test_parse_only():
    assert parse_only("1, 5,17-19") == {1, 5, 17, 18, 19}
    assert parse_only(None) is None


# ---------------------------------------------------------------- fixture and runner (mock LLM)


async def test_fixture_matches_the_plan():
    fx = await build_fixture()
    s = fx.portfolio.get_summary()
    assert s.cash_balance == 550
    assert s.total_value == pytest.approx(10350)
    assert s.total_pnl == pytest.approx(350)
    assert {p.ticker: p.current_price for p in s.positions} == {"AAPL": 190, "NVDA": 800, "JPM": 195}
    assert fx.cache.get_price("TSLA") == 250 and fx.cache.get_price("MSFT") == 420
    assert len(fx.watchlist.tickers()) == 10


def test_unknown_ticker_price_is_stable():
    assert price_for("ZZZZZ") == price_for("ZZZZZ")
    assert 50 <= price_for("ZZZZZ") <= 300


async def test_run_question_with_mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    q = {"id": 1, "group": "trade_intent", "message": "Buy 1 TSLA", "preceding": None}
    rec = await run_question(q, run=1)
    assert rec["requested_trades"] == [trade("TSLA", "buy", 1.0)]
    assert rec["fills"][0]["price"] == 250
    assert rec["cash_after"] == pytest.approx(300)
    assert "Total value: $10,350.00" in rec["context"]
    assert rec["llm_error"] is None


# ---------------------------------------------------------------- report: provider errors


def test_provider_errors_are_reported_separately(tmp_path):
    from eval.report import status, write_summary

    q = {"id": 1, "group": "no_trade", "message": "Hi", "expected": "No card", "check": {"no_trade": True}}
    base = record(question_id=1, group="no_trade", run=1, model="m", message="Hi",
                  latency_ms=1000, prompt_tokens=10, completion_tokens=5)
    ok = {**base, "passed": True, "reasons": []}
    err = {**base, "run": 2, "llm_error": "APIError 402", "passed": False, "reasons": ["AI call failed"]}
    assert (status(ok), status(err)) == ("pass", "error")
    meta = {"label": "t", "model": "m", "runs": 2, "started": "now",
            "price": {"provider": "x", "input_per_m": 1.0, "output_per_m": 1.0}}
    text = write_summary(tmp_path / "summary.md", meta, [ok, err], {1: q}, [])
    assert "| Calls answered | 1/2 (50%) — NOT VALID" in text
    assert "| Runs passed (of answered) | 1/1 (100%) |" in text
    assert "## Provider errors (1)" in text and "## Failures (0)" in text


def test_retry_errors_reruns_only_failed_calls(tmp_path, monkeypatch):
    import argparse

    from eval.report import load_runs
    from eval.run_eval import load_questions, retry_errors

    monkeypatch.setenv("LLM_MOCK", "true")
    good = record(question_id=1, group="trade_intent", run=1, model="m", message="Buy 1 TSLA",
                  latency_ms=5, prompt_tokens=0, completion_tokens=0,
                  requested_trades=[trade("TSLA", "buy", 1.0)], marker="kept")
    bad = {**good, "run": 2, "llm_error": "APIError 402", "requested_trades": [], "marker": "old"}
    (tmp_path / "runs.jsonl").write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n", encoding="utf-8")
    meta = {"label": "t", "model": "m", "mock": True, "runs": 2, "started": "now", "max_tokens": None,
            "price": {"provider": "mock", "input_per_m": 0.0, "output_per_m": 0.0}, "skipped_ids": []}
    (tmp_path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    by_id = {q["id"]: q for q in load_questions()}
    retry_errors(tmp_path, by_id, argparse.Namespace(delay=0.0, concurrency=1))

    runs = load_runs(tmp_path / "runs.jsonl")
    assert [r["run"] for r in runs] == [1, 2]
    assert runs[0]["marker"] == "kept"  # answered call untouched
    assert runs[1]["llm_error"] is None and runs[1]["requested_trades"] == [trade("TSLA", "buy", 1.0)]
    saved = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert saved["retries"][0]["recovered"] == 1
    assert "| Every question answered at least once | yes |" in (tmp_path / "summary.md").read_text(encoding="utf-8")
