"""Orchestrator LLM call: the kwargs handed to litellm.acompletion."""

import litellm
import pytest

from app.agents.orchestrator import EXTRA_BODY, MODEL, OrchestratorAgent
from app.db import Database


@pytest.fixture
def orchestrator(monkeypatch):
    # call_llm only needs the DB handle (for audit logging); the sibling agents are unused.
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    db = Database(":memory:")
    db.init_schema()
    return OrchestratorAgent(db, portfolio=None, analyzer=None, risk=None, watchlist=None)


# Minimal stand-in for a litellm ModelResponse: resp.choices[0].message.content.
class _Message:
    content = '{"message": "ok", "trades": [], "watchlist_changes": []}'


class _Choice:
    message = _Message()


class _Response:
    choices = [_Choice()]


@pytest.fixture
def captured(monkeypatch):
    """Record the kwargs of the single acompletion call and return a valid structured response."""
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return _Response()

    # call_llm imports acompletion lazily from the module, so patching here is enough.
    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return calls


async def test_reasoning_effort_is_explicitly_allowed(orchestrator, captured):
    """litellm's model map no longer lists reasoning_effort for this model, so passing it
    without allowed_openai_params raises UnsupportedParamsError before the request is sent."""
    await orchestrator.call_llm([{"role": "user", "content": "hi"}], "hi")

    assert len(captured) == 1
    assert captured[0]["allowed_openai_params"] == ["reasoning_effort"]
    assert captured[0]["reasoning_effort"] == "low"


async def test_model_and_provider_routing_unchanged(orchestrator, captured):
    out = await orchestrator.call_llm([{"role": "user", "content": "hi"}], "hi")

    assert captured[0]["model"] == MODEL
    assert captured[0]["extra_body"] == EXTRA_BODY
    assert out.message == "ok"
