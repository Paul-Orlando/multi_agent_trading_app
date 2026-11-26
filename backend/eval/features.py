"""Which features from the redesign plan exist yet. Questions needing anything else are skipped.

Add a feature name here in the step that builds it (and give its questions a "check" in
questions.json), so its questions start counting.
"""

from __future__ import annotations

ALL_FEATURES = {
    "none",
    "order_cards",
    "auto_execute",
    "orders_alerts",
    "support_agent",
    "analytics",
    "market_events",
}

BUILT_FEATURES: set[str] = {"none"}


def is_applicable(question: dict, built: set[str] | None = None) -> bool:
    """A question runs only if its feature is built and it has a check to grade against."""
    built = BUILT_FEATURES if built is None else built
    return question.get("requires", "none") in built and question.get("check") is not None
