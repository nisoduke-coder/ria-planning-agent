"""Tests for the portfolio analysis engine (no AI)."""

from ria_planner.models import Holding
from ria_planner.portfolio import TARGET_ALLOCATIONS, analyze_portfolio

HOLDINGS = [
    Holding("S&P 500 Index Fund", 180000, "equity"),
    Holding("Tech Growth ETF", 90000, "equity"),
    Holding("Total Bond Fund", 60000, "fixed_income"),
    Holding("Money Market", 40000, "cash"),
    Holding("REIT Fund", 30000, "real_estate"),
]


def test_total_value():
    a = analyze_portfolio(HOLDINGS, "moderate")
    assert a.total_value == 400000


def test_current_allocation_sums_to_100():
    a = analyze_portfolio(HOLDINGS, "moderate")
    assert abs(sum(a.current_pct.values()) - 100) < 0.01


def test_rebalancing_trades_net_to_zero():
    """Buys and sells must cancel — rebalancing doesn't add or remove money."""
    a = analyze_portfolio(HOLDINGS, "moderate")
    assert abs(sum(a.rebalancing.values())) < 1.0


def test_drift_matches_current_minus_target():
    a = analyze_portfolio(HOLDINGS, "moderate")
    for c in a.classes:
        assert abs(a.drift[c] - (a.current_pct[c] - a.target_pct[c])) < 0.01


def test_concentration_flag():
    a = analyze_portfolio(HOLDINGS, "moderate")
    # S&P 500 is 180k/400k = 45% -> over the 25% concentration threshold.
    assert any("Concentration" in f for f in a.flags)
    assert a.largest_name == "S&P 500 Index Fund"


def test_target_models_sum_to_100():
    for risk, alloc in TARGET_ALLOCATIONS.items():
        assert sum(alloc.values()) == 100, risk


def test_aggressive_targets_more_equity_than_conservative():
    a_agg = analyze_portfolio(HOLDINGS, "aggressive")
    a_con = analyze_portfolio(HOLDINGS, "conservative")
    assert a_agg.target_pct["equity"] > a_con.target_pct["equity"]
