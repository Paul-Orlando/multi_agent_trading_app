"""Grading: mainly on state (requested trades, fills, watchlist), with number checks on the reply.

A run record (see eval/runner.py) holds the context the model was given, the model's own text,
the full reply the visitor saw (model text plus any failure notes the app appends), the trades
the model requested, the trades that filled and the watchlist afterwards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Trade quantities match within 1%.
QTY_TOLERANCE = 0.01

DEFAULT_WATCHLIST = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]

# A number, optionally signed, optionally with $ before and %/k/m after. Commas allowed.
_NUM_RE = re.compile(
    r"(?<![\w.,])(?<!\w[-−])"
    r"(?P<sign>[-+−])?"
    r"(?P<dollar>\$)?\s?"
    r"(?P<int>\d{1,3}(?:,\d{3})+|\d+)"
    r"(?P<dec>\.\d+)?"
    r"(?:\s?(?P<suffix>%|[kK](?![a-zA-Z])|[mM](?![a-zA-Z])))?"
    r"(?![A-Za-z0-9])"  # not glued to a following word: "120b", "3rd"
)


@dataclass(frozen=True)
class Figure:
    value: float  # signed value, suffix applied
    step: float  # precision as written: "38.6" -> 0.1, "$10.4k" -> 100
    kind: str  # "dollar", "percent" or "plain"
    signed: bool  # an explicit + or - was written
    raw: str


def extract_figures(text: str) -> list[Figure]:
    out = []
    for m in _NUM_RE.finditer(text or ""):
        digits = m.group("int").replace(",", "")
        dec = m.group("dec") or ""
        value = float(digits + dec)
        step = 10.0 ** -(len(dec) - 1) if dec else 1.0
        suffix = (m.group("suffix") or "").lower()
        mult = {"k": 1_000.0, "m": 1_000_000.0}.get(suffix, 1.0)
        value *= mult
        step *= mult
        sign = m.group("sign")
        if sign in ("-", "−"):
            value = -value
        kind = "percent" if suffix == "%" else "dollar" if m.group("dollar") else "plain"
        out.append(Figure(value, step, kind, sign is not None, m.group(0).strip()))
    return out


def figure_matches(fig: Figure, target: float, target_step: float = 0.0) -> bool:
    """True if `fig` is `target` as written, allowing rounding to either side's precision.

    A sign is only compared when the reply wrote one: "up $200" matches +200, "-$200" does not.
    """
    if fig.signed and target != 0 and (fig.value < 0) != (target < 0):
        return False
    tolerance = max(fig.step, target_step) / 2 + 1e-9
    return abs(abs(fig.value) - abs(target)) <= tolerance


def reply_has_figure(reply: str, target: float) -> bool:
    return any(figure_matches(f, target) for f in extract_figures(reply))


def unsupported_figures(model_message: str, context: str) -> list[str]:
    """Dollar and percentage figures in the model's text that match no number in its context."""
    supported = extract_figures(context)
    return [
        f.raw
        for f in extract_figures(model_message)
        if f.kind in ("dollar", "percent")
        and not any(figure_matches(f, s.value, s.step) for s in supported)
    ]


def trades_match(requested: list[dict], expected: list[dict]) -> tuple[bool, str]:
    """Requested trades equal the expected ones as a set: ticker, side, quantity within 1%."""
    if len(requested) != len(expected):
        return False, f"expected {len(expected)} trade(s), model requested {len(requested)}"
    remaining = list(requested)
    for exp in expected:
        hit = next(
            (
                r
                for r in remaining
                if str(r["ticker"]).upper() == exp["ticker"]
                and r["side"] == exp["side"]
                and abs(float(r["quantity"]) - exp["quantity"]) <= QTY_TOLERANCE * exp["quantity"]
            ),
            None,
        )
        if hit is None:
            return False, f"no requested trade matching {exp['side']} {exp['quantity']:g} {exp['ticker']}"
        remaining.remove(hit)
    return True, ""


_POEM_LINE = re.compile(r"^(?![-*\d•]).{1,60}$")


def looks_like_poem(text: str) -> bool:
    """Four or more consecutive short lines that aren't list items."""
    run = 0
    for line in (text or "").splitlines():
        line = line.strip()
        if line and _POEM_LINE.match(line):
            run += 1
            if run >= 4:
                return True
        else:
            run = 0
    return False


def _fmt_trade(t: dict) -> str:
    return f"{t['side']} {float(t['quantity']):g} {t['ticker']}"


def grade(question: dict, record: dict) -> tuple[bool, list[str]]:
    """Return (passed, reasons for failure)."""
    check = question["check"]
    reasons: list[str] = []
    reply = record.get("reply") or ""
    requested = record.get("requested_trades") or []
    fills = record.get("fills") or []
    watchlist = record.get("watchlist_after") or []

    if record.get("llm_error"):
        return False, [f"AI call failed: {record['llm_error']}"]

    if "trades" in check:
        ok, why = trades_match(requested, check["trades"])
        if not ok:
            got = ", ".join(_fmt_trade(t) for t in requested) or "none"
            reasons.append(f"{why} (requested: {got})")
    if check.get("no_trade") and requested:
        reasons.append("trade requested: " + ", ".join(_fmt_trade(t) for t in requested))
    if check.get("no_fill") and fills:
        reasons.append("trade filled: " + ", ".join(_fmt_trade(t) for t in fills))

    for target in check.get("figures", []):
        if not reply_has_figure(reply, target):
            reasons.append(f"expected figure {target:g} not in reply")
    for ticker in check.get("tickers", []):
        if not re.search(rf"\b{re.escape(ticker)}\b", reply):
            reasons.append(f"reply doesn't name {ticker}")
    if "max_unsupported" in check:
        bad = record.get("unsupported") or []
        if len(bad) > check["max_unsupported"]:
            reasons.append("figures not in the data: " + ", ".join(bad))

    patterns = check.get("reply_any")
    if patterns and not any(re.search(p, reply, re.I) for p in patterns):
        reasons.append("reply lacks the expected explanation/redirect")
    for p in check.get("reply_none", []):
        m = re.search(p, reply, re.I)
        if m:
            reasons.append(f"reply contains '{m.group(0)}'")
    if check.get("not_poem") and looks_like_poem(record.get("model_message") or reply):
        reasons.append("reply looks like a poem")

    for t in check.get("watchlist_includes", []):
        if t not in watchlist:
            reasons.append(f"{t} not on the watchlist afterwards")
    for t in check.get("watchlist_excludes", []):
        if t in watchlist:
            reasons.append(f"{t} still on the watchlist afterwards")
    if check.get("watchlist_unchanged") and sorted(watchlist) != sorted(DEFAULT_WATCHLIST):
        reasons.append(f"watchlist changed: {', '.join(watchlist)}")
    if check.get("reply_lists_watchlist"):
        missing = [t for t in DEFAULT_WATCHLIST if not re.search(rf"\b{t}\b", reply)]
        if missing:
            reasons.append("reply omits " + ", ".join(missing))

    return not reasons, reasons
