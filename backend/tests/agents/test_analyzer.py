"""Analyzer: best and worst positions are ranked by percentage return, with both figures given."""

from eval.fixture import build_fixture


async def test_worst_and_best_ranked_by_percentage_return():
    # Test portfolio: AAPL +$50 (+2.7%), JPM +$100 (+2.6%), NVDA +$200 (+5.3%).
    # By dollars AAPL would be worst; by percentage it is JPM.
    fx = await build_fixture()
    summary = fx.portfolio.get_summary()
    report = fx.orchestrator.analyzer.analyze(summary, fx.watchlist.tickers())

    assert report.worst_performer.ticker == "JPM"
    assert report.best_performer.ticker == "NVDA"


async def test_prompt_context_gives_percentage_and_dollar_figures():
    fx = await build_fixture()
    analyzer = fx.orchestrator.analyzer
    text = analyzer.to_prompt_context(analyzer.analyze(fx.portfolio.get_summary(), []))

    assert "Worst (by % return): JPM (+2.6%, $+100.00)" in text
    assert "Best (by % return): NVDA (+5.3%, $+200.00)" in text
