"""The deterministic retirement engine.

No AI here — just transparent, auditable math an advisor could check by hand.
Keeping the numbers OUT of the language model matters in this industry: the
projections must be reproducible and explainable, not "the AI said so."

Two views of "success":
  * run_plan()    — accumulation snapshot: do they hit a target nest egg at 67?
  * monte_carlo() — full lifecycle: does the money LAST through retirement?
The lifecycle view is the gold standard, because it captures sequence-of-returns
risk (a bad market right before/after retirement) that a single number hides.

Everything is illustrative, not advice. See the disclaimer in cli.py.
"""

from dataclasses import dataclass, replace

import numpy as np

from .models import ClientProfile

# How bumpy a portfolio's returns are (annual standard deviation), by risk
# tolerance. More aggressive = higher average return but harder swings. These
# are illustrative industry-ballpark figures, not precise asset-class data.
VOLATILITY_BY_RISK = {
    "conservative": 0.07,
    "moderate": 0.11,
    "aggressive": 0.16,
}
DEFAULT_VOLATILITY = 0.11

# Where a glide path lands the portfolio by retirement (a conservative mix),
# and how many years before retirement the de-risking takes place over.
CONSERVATIVE_RETURN = 0.045   # gross, before fees
CONSERVATIVE_VOLATILITY = 0.07
GLIDE_YEARS = 10

# Guardrail (dynamic withdrawal) settings: never pull more than 5% of the
# current portfolio in a year, and never cut essential spending below 75% of
# the planned need.
GUARDRAIL_CEILING = 0.05
SPENDING_FLOOR_RATIO = 0.75

# Social Security: claiming later than full retirement age (67) raises the
# benefit; claiming earlier cuts it. Standard SSA adjustment factors.
SS_CLAIM_FACTORS = {62: 0.70, 67: 1.00, 70: 1.24}


# --------------------------------------------------------------------------- #
# Accumulation snapshot (the straight-line view)
# --------------------------------------------------------------------------- #


@dataclass
class PlanResults:
    projected_nest_egg: float          # portfolio value at retirement (nominal $)

    # First-retirement-year income picture (future $)
    gross_income_need: float           # total income needed
    guaranteed_income: float           # covered by Social Security / pension / other
    portfolio_income_need: float       # what the PORTFOLIO must provide

    target_nest_egg: float             # portfolio needed to fund portfolio_income_need
    surplus_or_gap: float              # projected - target  (negative = shortfall)
    on_track: bool

    required_monthly_contribution: float
    additional_monthly_needed: float

    years_to_retirement: int
    net_return: float
    sustainable_total_income: float


def _future_value(profile: ClientProfile) -> float:
    """Grow today's savings + monthly contributions to the retirement date."""
    years = profile.years_to_retirement
    months = years * 12
    annual_r = profile.net_return
    monthly_r = (1 + annual_r) ** (1 / 12) - 1

    fv_current = profile.current_savings * (1 + annual_r) ** years
    if monthly_r == 0:
        fv_contributions = profile.monthly_contribution * months
    else:
        fv_contributions = profile.monthly_contribution * (
            ((1 + monthly_r) ** months - 1) / monthly_r
        )
    return fv_current + fv_contributions


def _required_monthly_contribution(profile: ClientProfile, target: float) -> float:
    """Solve for the monthly contribution that reaches `target` by retirement."""
    years = profile.years_to_retirement
    months = years * 12
    annual_r = profile.net_return
    monthly_r = (1 + annual_r) ** (1 / 12) - 1

    fv_current = profile.current_savings * (1 + annual_r) ** years
    needed = max(target - fv_current, 0.0)
    if months == 0:
        return 0.0
    if monthly_r == 0:
        return needed / months
    annuity_factor = ((1 + monthly_r) ** months - 1) / monthly_r
    return needed / annuity_factor


def run_plan(profile: ClientProfile) -> PlanResults:
    """Accumulation snapshot: straight-line projection vs. a target nest egg."""
    years = profile.years_to_retirement
    inflate = (1 + profile.inflation) ** years

    gross_income_need = profile.annual_income * profile.income_replacement_ratio * inflate
    guaranteed_today = (
        profile.social_security_annual
        + profile.pension_annual
        + profile.other_retirement_income_annual
    )
    guaranteed_income = guaranteed_today * inflate
    portfolio_income_need = max(gross_income_need - guaranteed_income, 0.0)

    target_nest_egg = (
        portfolio_income_need / profile.withdrawal_rate
        if profile.withdrawal_rate > 0
        else float("inf")
    )
    projected = _future_value(profile)
    gap = projected - target_nest_egg
    required_monthly = _required_monthly_contribution(profile, target_nest_egg)

    return PlanResults(
        projected_nest_egg=projected,
        gross_income_need=gross_income_need,
        guaranteed_income=guaranteed_income,
        portfolio_income_need=portfolio_income_need,
        target_nest_egg=target_nest_egg,
        surplus_or_gap=gap,
        on_track=gap >= 0,
        required_monthly_contribution=required_monthly,
        additional_monthly_needed=max(required_monthly - profile.monthly_contribution, 0.0),
        years_to_retirement=years,
        net_return=profile.net_return,
        sustainable_total_income=projected * profile.withdrawal_rate + guaranteed_income,
    )


# --------------------------------------------------------------------------- #
# Full-lifecycle Monte Carlo: saving up, then spending down.
# --------------------------------------------------------------------------- #


@dataclass
class MonteCarloResults:
    probability_of_success: float   # share of paths where money lasted to age LE
    n_simulations: int

    # Spread of the nest egg AT retirement (nominal $):
    p10: float
    p50: float
    p90: float

    volatility: float               # starting annual return std-dev


def _year_params(profile: ClientProfile, years_until_retirement: int, glide_path: bool):
    """The (net mean return, volatility) to use for one simulated year.

    Without a glide path, the allocation stays put. With one, it drifts from the
    client's current mix toward a conservative mix over the final GLIDE_YEARS
    before retirement, then stays conservative through retirement.
    """
    start_return = profile.expected_return
    start_vol = VOLATILITY_BY_RISK.get(profile.risk_tolerance, DEFAULT_VOLATILITY)

    if not glide_path:
        return start_return - profile.annual_fee, start_vol

    if years_until_retirement >= GLIDE_YEARS:
        gross, vol = start_return, start_vol
    elif years_until_retirement <= 0:
        gross, vol = CONSERVATIVE_RETURN, CONSERVATIVE_VOLATILITY
    else:
        t = (GLIDE_YEARS - years_until_retirement) / GLIDE_YEARS  # 0 -> 1
        gross = start_return + (CONSERVATIVE_RETURN - start_return) * t
        vol = start_vol + (CONSERVATIVE_VOLATILITY - start_vol) * t
    return gross - profile.annual_fee, vol


def monte_carlo(
    profile: ClientProfile,
    n_simulations: int = 5_000,
    seed: int = 42,
    glide_path: bool = False,
    withdrawal_strategy: str = "fixed",
    ss_multiplier: float = 1.0,
) -> MonteCarloResults:
    """Simulate many full lifetimes at once; report how often the money lasts.

    Each path saves to retirement, then spends down to life expectancy with
    random yearly returns. This is vectorized with NumPy: instead of looping
    over each of the thousands of simulations, we hold all of them in arrays
    and advance them one year at a time together — the same math, but ~50-100x
    faster, which matters on a small cloud server. `seed` is fixed so results
    are reproducible and comparable across the what-if levers.
    """
    rng = np.random.default_rng(seed)
    n = n_simulations
    infl = profile.inflation
    years_acc = profile.years_to_retirement
    years_dec = profile.years_in_retirement
    annual_contribution = profile.monthly_contribution * 12

    # --- Accumulation: every path saves and grows until retirement ---
    portfolio = np.full(n, float(profile.current_savings))
    for y in range(years_acc):
        mean, vol = _year_params(profile, years_acc - y, glide_path)
        portfolio = portfolio * (1 + rng.normal(mean, vol, n)) + annual_contribution
    retirement_balance = portfolio.copy()

    guaranteed_today = (
        profile.social_security_annual * ss_multiplier
        + profile.pension_annual
        + profile.other_retirement_income_annual
    )

    # --- Decumulation: every path spends down through retirement ---
    alive = np.ones(n, dtype=bool)  # paths that haven't run out yet
    for y in range(years_dec):
        inflate = (1 + infl) ** (years_acc + y)

        base_need = profile.annual_income * profile.income_replacement_ratio
        if profile.retirement_age + y < 65:
            base_need += profile.pre_medicare_annual_cost   # bridge to Medicare
        if profile.ltc_annual_cost > 0 and y >= years_dec - profile.ltc_years:
            base_need += profile.ltc_annual_cost            # late-life care
        need = max(base_need * inflate - guaranteed_today * inflate, 0.0)

        if withdrawal_strategy == "dynamic":
            # Guardrails: in down markets, draw less (but never below essentials).
            ceiling = portfolio * GUARDRAIL_CEILING
            withdrawal = np.where(
                need <= ceiling, need, np.maximum(ceiling, need * SPENDING_FLOOR_RATIO)
            )
        else:
            withdrawal = need

        portfolio = np.where(alive, portfolio - withdrawal, 0.0)
        alive &= portfolio > 0
        mean, vol = _year_params(profile, -y, glide_path)
        portfolio = np.where(alive, portfolio * (1 + rng.normal(mean, vol, n)), 0.0)

    balances = np.sort(retirement_balance)

    def pct(p):
        return float(balances[int(round((p / 100.0) * (n - 1)))])

    return MonteCarloResults(
        probability_of_success=float(np.mean(alive)),
        n_simulations=n,
        p10=pct(10),
        p50=pct(50),
        p90=pct(90),
        volatility=VOLATILITY_BY_RISK.get(profile.risk_tolerance, DEFAULT_VOLATILITY),
    )


# --------------------------------------------------------------------------- #
# Scenarios & strategy comparisons: quantify the advisor's "what if" levers.
# --------------------------------------------------------------------------- #


@dataclass
class Scenario:
    label: str
    probability_of_success: float


@dataclass
class ClaimingOption:
    claim_age: int
    annual_benefit: float           # combined household SS at this claim age (today's $)
    probability_of_success: float


def scenarios(profile: ClientProfile) -> list:
    """Savings/timing levers: what if she works longer or saves more?"""
    variations = [
        ("Current plan", profile),
        ("Retire 2 years later", replace(profile, retirement_age=profile.retirement_age + 2)),
        ("Save $500/mo more", replace(profile, monthly_contribution=profile.monthly_contribution + 500)),
        (
            "Both (+2 yrs & +$500/mo)",
            replace(
                profile,
                retirement_age=profile.retirement_age + 2,
                monthly_contribution=profile.monthly_contribution + 500,
            ),
        ),
    ]
    return [
        Scenario(label, monte_carlo(p).probability_of_success)
        for label, p in variations
    ]


def strategy_comparison(profile: ClientProfile) -> list:
    """Method levers: glide-path de-risking and flexible (dynamic) spending."""
    combos = [
        ("Fixed spending, current allocation", False, "fixed"),
        ("Fixed spending, glide path", True, "fixed"),
        ("Flexible spending, current allocation", False, "dynamic"),
        ("Flexible spending, glide path", True, "dynamic"),
    ]
    return [
        Scenario(
            label,
            monte_carlo(profile, glide_path=glide, withdrawal_strategy=strat).probability_of_success,
        )
        for label, glide, strat in combos
    ]


def claiming_comparison(profile: ClientProfile) -> list:
    """Social Security timing: the effect of claiming at 62 vs 67 vs 70.

    Simplification: assumes benefits begin at retirement at the age-adjusted
    amount (bridge years between retirement and a later claim are not modeled).
    """
    options = []
    for claim_age, factor in sorted(SS_CLAIM_FACTORS.items()):
        prob = monte_carlo(profile, ss_multiplier=factor).probability_of_success
        options.append(
            ClaimingOption(
                claim_age=claim_age,
                annual_benefit=profile.social_security_annual * factor,
                probability_of_success=prob,
            )
        )
    return options
