"""Tests for the deterministic retirement engine.

Run with:  .venv/bin/python -m pytest -q
These cover the math only (no AI, no API key needed).
"""

from dataclasses import replace

from ria_planner.engine import (
    claiming_comparison,
    monte_carlo,
    run_plan,
    scenarios,
    strategy_comparison,
)
from ria_planner.models import ClientProfile

# A well-funded base client so probabilities sit in an interesting middle range.
BASE = ClientProfile(
    name="Test",
    current_age=48,
    retirement_age=67,
    annual_income=160000,
    current_savings=720000,
    monthly_contribution=3500,
    social_security_annual=48000,
    ltc_annual_cost=70000,
    income_replacement_ratio=0.70,
    expected_return=0.065,
    risk_tolerance="aggressive",
)


def test_net_return_subtracts_fees():
    p = replace(BASE, expected_return=0.06, annual_fee=0.01)
    assert abs(p.net_return - 0.05) < 1e-9


def test_run_plan_fields_consistent():
    r = run_plan(BASE)
    # Portfolio need = total need minus guaranteed income (never negative).
    assert r.portfolio_income_need >= 0
    assert abs((r.gross_income_need - r.guaranteed_income) - r.portfolio_income_need) < 1.0
    # Target nest egg = portfolio need / withdrawal rate.
    assert abs(r.target_nest_egg - r.portfolio_income_need / BASE.withdrawal_rate) < 1.0
    # Surplus/gap and on_track agree.
    assert r.on_track == (r.surplus_or_gap >= 0)


def test_more_savings_raises_projection():
    low = run_plan(replace(BASE, monthly_contribution=1000))
    high = run_plan(replace(BASE, monthly_contribution=5000))
    assert high.projected_nest_egg > low.projected_nest_egg


def test_monte_carlo_probability_is_a_fraction():
    mc = monte_carlo(BASE)
    assert 0.0 <= mc.probability_of_success <= 1.0
    assert mc.p10 <= mc.p50 <= mc.p90  # percentiles ordered


def test_monte_carlo_is_reproducible():
    assert (
        monte_carlo(BASE).probability_of_success
        == monte_carlo(BASE).probability_of_success
    )


def test_saving_more_never_lowers_success():
    base = monte_carlo(BASE).probability_of_success
    more = monte_carlo(replace(BASE, monthly_contribution=BASE.monthly_contribution + 2000))
    assert more.probability_of_success >= base


def test_scenarios_and_strategy_shape():
    assert len(scenarios(BASE)) == 4
    assert len(strategy_comparison(BASE)) == 4
    for s in scenarios(BASE) + strategy_comparison(BASE):
        assert 0.0 <= s.probability_of_success <= 1.0


def test_claiming_models_the_bridge():
    """Delaying past retirement should NOT be a free win: the gap between
    claiming at 67 and 70 must be modest (the bridge cost is now counted),
    not the large runaway it was when the bridge was ignored."""
    by_age = {c.claim_age: c.probability_of_success for c in claiming_comparison(BASE)}
    # Bigger benefit at 70 than 62 (factors applied).
    assert by_age[70] >= by_age[62]
    # The 67->70 step is small because the 3-year bridge offsets the bigger benefit.
    assert (by_age[70] - by_age[67]) < 0.10


def test_zero_total_savings_still_runs():
    broke = replace(BASE, current_savings=0, monthly_contribution=0, social_security_annual=0)
    mc = monte_carlo(broke)
    assert 0.0 <= mc.probability_of_success <= 1.0
