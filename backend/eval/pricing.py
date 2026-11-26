"""OpenRouter list prices, fetched from its public models API (no key needed)."""

from __future__ import annotations

import json
import urllib.request

ENDPOINTS_URL = "https://openrouter.ai/api/v1/models/{slug}/endpoints"


def openrouter_slug(model: str) -> str:
    """'openrouter/openai/gpt-oss-120b' -> 'openai/gpt-oss-120b'."""
    return model.removeprefix("openrouter/")


def fetch_price(model: str, preferred_provider: str | None = None, timeout: float = 15) -> dict:
    """USD per million tokens for the model, from the preferred provider's endpoint if listed.

    Returns {"provider", "input_per_m", "output_per_m", "source"}; prices are None if unavailable.
    """
    slug = openrouter_slug(model)
    url = ENDPOINTS_URL.format(slug=slug)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "copperline-eval"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            endpoints = json.load(r)["data"]["endpoints"]
    except Exception as e:  # noqa: BLE001 - pricing is best effort
        return {"provider": None, "input_per_m": None, "output_per_m": None,
                "source": f"unavailable ({e.__class__.__name__})"}
    chosen = None
    if preferred_provider:
        chosen = next(
            (e for e in endpoints if preferred_provider.lower() in str(e.get("provider_name", "")).lower()),
            None,
        )
    chosen = chosen or (endpoints[0] if endpoints else None)
    if not chosen:
        return {"provider": None, "input_per_m": None, "output_per_m": None, "source": url}
    p = chosen.get("pricing", {})
    return {
        "provider": chosen.get("provider_name"),
        "input_per_m": float(p.get("prompt", 0)) * 1e6,
        "output_per_m": float(p.get("completion", 0)) * 1e6,
        "source": url,
    }


def cost_usd(prompt_tokens: int, completion_tokens: int, price: dict) -> float | None:
    if price.get("input_per_m") is None:
        return None
    return (prompt_tokens * price["input_per_m"] + completion_tokens * price["output_per_m"]) / 1e6
