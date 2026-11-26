"""The plan's test portfolio, rebuilt fresh in a throwaway in-memory database for every question.

Started with $10,000; holds 10 AAPL (avg $185), 5 NVDA (avg $760), 20 JPM (avg $190); cash $550.
Prices are fixed (no simulator drift), so total value is $10,350 and P&L +$350.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.agents import AnalyzerAgent, OrchestratorAgent, PortfolioAgent, RiskAgent, WatchlistAgent
from app.agents.base import USER_ID, new_id, now_iso
from app.db import Database
from app.market import MarketDataSource, PriceCache
from app.market.seed_prices import SEED_PRICES

STARTING_CASH = 10_000.0
CASH = 550.0
POSITIONS = {"AAPL": (10, 185.0), "NVDA": (5, 760.0), "JPM": (20, 190.0)}
# The plan's frozen prices; the other default-watchlist tickers keep their seed prices.
FIXED_PRICES = {
    **SEED_PRICES,
    "AAPL": 190.0,
    "NVDA": 800.0,
    "JPM": 195.0,
    "TSLA": 250.0,
    "MSFT": 420.0,
    "AMZN": 185.0,
}


def price_for(ticker: str) -> float:
    """Fixed price for known tickers. Unknown tickers mirror today's simulator, which prices any
    ticker it is asked for at a random $50-$300; here the 'random' price is seeded by the ticker
    so every run sees the same number."""
    if ticker in FIXED_PRICES:
        return FIXED_PRICES[ticker]
    return round(random.Random(ticker).uniform(50.0, 300.0), 2)


class FixedPriceSource(MarketDataSource):
    """Market data source that writes one fixed price per ticker and never moves it."""

    def __init__(self, cache: PriceCache) -> None:
        self._cache = cache
        self._tickers: set[str] = set()

    async def start(self, tickers: list[str]) -> None:
        for t in tickers:
            await self.add_ticker(t)

    async def stop(self) -> None:
        pass

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self._tickers:
            self._tickers.add(ticker)
            self._cache.update(ticker, price_for(ticker))

    async def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return sorted(self._tickers)


@dataclass
class Fixture:
    db: Database
    cache: PriceCache
    source: FixedPriceSource
    portfolio: PortfolioAgent
    watchlist: WatchlistAgent
    orchestrator: OrchestratorAgent


async def build_fixture(preceding: dict | None = None) -> Fixture:
    """Fresh database + agents wired exactly as in app.main, with the test portfolio loaded."""
    db = Database(":memory:")
    db.init_schema()  # default watchlist comes from the schema seed
    db.execute(
        "UPDATE portfolio_state SET cash_balance=?, starting_cash=? WHERE user_id=?",
        (CASH, STARTING_CASH, USER_ID),
    )
    for ticker, (qty, avg) in POSITIONS.items():
        db.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, current_price)"
            " VALUES (?,?,?,?,?,?)",
            (new_id(), USER_ID, ticker, qty, avg, FIXED_PRICES[ticker]),
        )
    if preceding:
        # An earlier exchange, replayed into the prompt as chat history.
        db.execute(
            "INSERT INTO chat_messages (id, user_id, user_message, ai_response, executed_trades,"
            " watchlist_changes, created_at) VALUES (?,?,?,?,?,?,?)",
            (new_id(), USER_ID, preceding["user"], preceding["assistant"], "[]", "[]", now_iso()),
        )

    cache = PriceCache()
    source = FixedPriceSource(cache)
    watchlist = WatchlistAgent(db, cache, source)
    portfolio = PortfolioAgent(db, cache)
    risk = RiskAgent(db, cache)
    analyzer = AnalyzerAgent(db, cache, risk.limits.warn_position_pct)
    orchestrator = OrchestratorAgent(db, portfolio, analyzer, risk, watchlist)
    await source.start(watchlist.tracked_tickers())
    return Fixture(db, cache, source, portfolio, watchlist, orchestrator)
