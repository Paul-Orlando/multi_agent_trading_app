"""Run one question through the real OrchestratorAgent and record what happened."""

from __future__ import annotations

import os
import re
import time
from contextvars import ContextVar

from app.agents import orchestrator as orchestrator_module

from .fixture import build_fixture
from .grader import unsupported_figures

# Token usage of the LLM calls made inside the current question (a list per asyncio task).
_usage: ContextVar[list | None] = ContextVar("eval_usage", default=None)
_patched = False


def eval_max_tokens() -> int | None:
    """EVAL_MAX_TOKENS env var: a reply cap for evaluation calls only. Unset = no cap (as the app)."""
    raw = os.environ.get("EVAL_MAX_TOKENS", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def install_usage_capture() -> None:
    """Wrap litellm.acompletion once so each call's token usage is recorded for its question.

    The orchestrator imports acompletion lazily from the litellm module, so wrapping the module
    attribute is enough; the call itself is unchanged."""
    global _patched
    if _patched:
        return
    import litellm

    litellm.suppress_debug_info = True
    original = litellm.acompletion

    async def acompletion_with_usage(*args, **kwargs):
        # Eval-only reply cap (unset by default). OpenRouter reserves credit per request for the
        # longest possible reply; without a cap that reservation can trigger its 402
        # "in-flight budget" error. The app itself never sets max_tokens.
        cap = eval_max_tokens()
        if cap:
            kwargs.setdefault("max_tokens", cap)
        resp = await original(*args, **kwargs)
        sink = _usage.get()
        usage = getattr(resp, "usage", None)
        if sink is not None and usage is not None:
            sink.append(
                {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    # OpenRouter reports which upstream provider actually served the call.
                    "provider": getattr(resp, "provider", None),
                }
            )
        return resp

    litellm.acompletion = acompletion_with_usage
    _patched = True


def _mask(text: str) -> str:
    """Results are committed, so anything shaped like an API key is masked and length capped."""
    return re.sub(r"sk-[A-Za-z0-9_-]{4,}", "sk-***", text)[:500]


def set_model(model: str | None) -> str:
    """Point the orchestrator at another model for this process; returns the model in use."""
    if model:
        orchestrator_module.MODEL = model
    return orchestrator_module.MODEL


async def run_question(question: dict, run: int) -> dict:
    fx = await build_fixture(question.get("preceding"))
    orch = fx.orchestrator
    seen: dict = {}

    # Observe the single LLM call: the prompt it was given and the structured output it returned.
    original_call = orch.call_llm

    async def observed_call(messages, user_text=""):
        seen["messages"] = messages
        out = await original_call(messages, user_text)
        seen["llm"] = out
        return out

    orch.call_llm = observed_call

    usage: list = []
    token = _usage.set(usage)
    start = time.perf_counter()
    try:
        response = await orch.handle_message(question["message"])
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        _usage.reset(token)

    llm = seen.get("llm")
    # Everything the model was given except the static rules prompt: live context, history, message.
    context = "\n".join(m["content"] for m in seen.get("messages", [])[1:])
    model_message = llm.message if llm else ""
    llm_error = None
    if llm is None:
        # The llm_call log has the provider's message; handle_message only has the class name.
        row = fx.db.query_one(
            "SELECT error FROM agent_logs WHERE agent_id='orchestrator' AND status='error'"
            " ORDER BY (action='llm_call') DESC, created_at DESC, rowid DESC LIMIT 1"
        )
        llm_error = _mask((row or {}).get("error") or "no model output")

    record = {
        "question_id": question["id"],
        "group": question["group"],
        "run": run,
        "model": orchestrator_module.MODEL,
        "message": question["message"],
        "context": context,
        "model_message": model_message,
        "reply": response.message,
        "requested_trades": [t.model_dump() for t in llm.trades] if llm else [],
        "requested_watchlist": [w.model_dump() for w in llm.watchlist_changes] if llm else [],
        "trade_results": [t.model_dump() for t in response.executed_trades],
        "fills": [
            {"ticker": t.ticker, "side": t.side, "quantity": t.quantity, "price": t.price}
            for t in response.executed_trades
            if t.ok
        ],
        "watchlist_after": fx.watchlist.tickers(),
        "cash_after": fx.portfolio.get_summary().cash_balance,
        "latency_ms": latency_ms,
        "prompt_tokens": sum(u["prompt_tokens"] for u in usage),
        "completion_tokens": sum(u["completion_tokens"] for u in usage),
        "llm_calls": len(usage),
        "provider": ", ".join(sorted({u["provider"] for u in usage if u.get("provider")})) or None,
        "max_tokens": eval_max_tokens(),
        "llm_error": llm_error,
    }
    record["unsupported"] = unsupported_figures(model_message, context)
    fx.db.close()
    return record
