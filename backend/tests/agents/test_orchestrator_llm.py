"""Orchestrator LLM call: the request handed to litellm.acompletion, the prompt, and failure handling."""

import json

import litellm
import pytest

from app.agents.orchestrator import (
    AI_UNAVAILABLE_MESSAGE,
    APP_TITLE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_TIMEOUT_SECONDS,
    LLMSettings,
    OrchestratorAgent,
)
from app.db import Database
from eval.fixture import build_fixture

SETTINGS_ENV = (
    "OPENROUTER_MODEL", "OPENROUTER_PROVIDER", "OPENROUTER_MAX_TOKENS", "OPENROUTER_TIMEOUT",
    "APP_URL", "RAILWAY_PUBLIC_DOMAIN",
)


@pytest.fixture(autouse=True)
def clean_settings_env(monkeypatch):
    for name in SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def orchestrator(monkeypatch):
    # call_llm only needs the DB handle (for audit logging); the sibling agents are unused.
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    db = Database(":memory:")
    db.init_schema()
    return OrchestratorAgent(db, portfolio=None, analyzer=None, risk=None, watchlist=None)


# Minimal stand-ins for a litellm ModelResponse.
class _Message:
    content = '{"message": "ok", "trades": [], "watchlist_changes": []}'


class _Choice:
    message = _Message()


class _Usage:
    prompt_tokens = 1100
    completion_tokens = 40
    cost = 0.000415


class _Response:
    choices = [_Choice()]
    usage = _Usage()
    provider = "Cerebras"
    model = "openai/gpt-oss-120b"


@pytest.fixture
def captured(monkeypatch):
    """Record the kwargs of each acompletion call and return a valid structured response."""
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return _Response()

    # call_llm imports acompletion lazily from the module, so patching here is enough.
    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return calls


# ---------------------------------------------------------------- the request


async def test_request_uses_cerebras_only_with_no_fallbacks(orchestrator, captured):
    out = await orchestrator.call_llm([{"role": "user", "content": "hi"}], "hi")

    assert out.message == "ok"
    assert len(captured) == 1
    req = captured[0]
    assert req["model"] == "openrouter/openai/gpt-oss-120b"
    assert req["extra_body"] == {
        "provider": {"order": ["cerebras"], "allow_fallbacks": False, "require_parameters": True}
    }


async def test_request_has_reply_cap_timeout_and_no_retries(orchestrator, captured):
    await orchestrator.call_llm([{"role": "user", "content": "hi"}], "hi")

    req = captured[0]
    assert req["max_tokens"] == DEFAULT_MAX_TOKENS == 1500
    assert req["timeout"] == DEFAULT_TIMEOUT_SECONDS == 30
    assert req["num_retries"] == 0 and req["max_retries"] == 0


async def test_reasoning_effort_is_explicitly_allowed(orchestrator, captured):
    """With litellm's downloaded price list, reasoning_effort for this model is rejected before the
    request is sent unless it is explicitly allowed."""
    await orchestrator.call_llm([{"role": "user", "content": "hi"}], "hi")

    assert captured[0]["allowed_openai_params"] == ["reasoning_effort"]
    assert captured[0]["reasoning_effort"] == "low"


async def test_request_carries_app_labels(orchestrator, captured, monkeypatch):
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "finally.example.app")
    await orchestrator.call_llm([{"role": "user", "content": "hi"}], "hi")

    assert captured[0]["extra_headers"] == {
        "HTTP-Referer": "https://finally.example.app",
        "X-Title": APP_TITLE,
    }
    assert APP_TITLE == "FinAlly"


def test_settings_defaults_and_env_overrides(monkeypatch):
    s = LLMSettings.from_env()
    assert (s.model, s.provider, s.max_tokens, s.timeout) == (
        DEFAULT_MODEL, DEFAULT_PROVIDER, 1500, 30.0
    )
    assert s.app_url == "http://localhost:8000"

    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("OPENROUTER_PROVIDER", "groq")
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS", "800")
    monkeypatch.setenv("OPENROUTER_TIMEOUT", "12.5")
    monkeypatch.setenv("APP_URL", "https://demo.example")
    s = LLMSettings.from_env()
    assert s.litellm_model == "openrouter/openai/gpt-oss-20b"
    assert s.provider_routing()["order"] == ["groq"]
    assert (s.max_tokens, s.timeout, s.app_url) == (800, 12.5, "https://demo.example")


@pytest.mark.parametrize("bad", ["", "abc", "0", "-5"])
def test_malformed_numeric_settings_fall_back_to_defaults(monkeypatch, bad):
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS", bad)
    monkeypatch.setenv("OPENROUTER_TIMEOUT", bad)
    s = LLMSettings.from_env()
    assert (s.max_tokens, s.timeout) == (1500, 30.0)


async def test_provider_tokens_and_cost_are_logged(orchestrator, captured):
    await orchestrator.call_llm([{"role": "user", "content": "hi"}], "hi")

    row = orchestrator.db.query_one(
        "SELECT output FROM agent_logs WHERE action='llm_call' AND status='success'"
    )
    out = json.loads(row["output"])
    assert out["provider"] == "Cerebras"
    assert (out["prompt_tokens"], out["completion_tokens"]) == (1100, 40)
    assert out["cost_usd"] == pytest.approx(0.000415)


# ---------------------------------------------------------------- the prompt


async def test_prompt_is_one_system_message_with_rules_and_portfolio():
    fx = await build_fixture()
    orch = fx.orchestrator
    summary = fx.portfolio.get_summary()
    entries = fx.watchlist.list_with_prices()
    analysis = orch.analyzer.to_prompt_context(orch.analyzer.analyze(summary, [e.ticker for e in entries]))
    msgs = orch.build_prompt("How much cash do I have?", summary, analysis, entries, [])

    assert [m["role"] for m in msgs] == ["system", "user"]
    system = msgs[0]["content"]
    assert system.startswith("You are FinAlly")  # the rules come first
    assert "Cash: $550.00" in system and "Total value: $10,350.00" in system


# ---------------------------------------------------------------- failures


class _RefusedError(Exception):
    status_code = 402


async def test_provider_refusal_shows_plain_message_and_logs_details(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls = []

    async def refuse(**kwargs):
        calls.append(kwargs)
        raise _RefusedError("This request requires more credits, or fewer max_tokens.")

    monkeypatch.setattr(litellm, "acompletion", refuse)
    fx = await build_fixture()

    response = await fx.orchestrator.handle_message("Buy 1 TSLA")

    assert response.message == AI_UNAVAILABLE_MESSAGE
    assert "_RefusedError" not in response.message and "402" not in response.message
    assert response.executed_trades == [] and fx.portfolio.get_summary().cash_balance == 550
    assert len(calls) == 1  # no retry on a provider refusal
    errors = [r["error"] for r in fx.db.query("SELECT error FROM agent_logs WHERE status='error'")]
    assert any("status 402" in e and "more credits" in e for e in errors)


async def test_malformed_output_is_retried_once(orchestrator, monkeypatch):
    calls = []

    class _Bad(_Response):
        class choices_item:  # noqa: N801
            class message:  # noqa: N801
                content = "not json"

        choices = [choices_item()]

    async def bad(**kwargs):
        calls.append(kwargs)
        return _Bad()

    monkeypatch.setattr(litellm, "acompletion", bad)
    with pytest.raises(Exception, match="malformed model output"):
        await orchestrator.call_llm([{"role": "user", "content": "hi"}], "hi")
    assert len(calls) == 2


async def test_missing_key_shows_plain_message(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fx = await build_fixture()
    response = await fx.orchestrator.handle_message("Buy 1 TSLA")
    assert response.message == AI_UNAVAILABLE_MESSAGE
