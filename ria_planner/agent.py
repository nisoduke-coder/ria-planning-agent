"""The AI layer: Claude drafts the advisor-facing financial plan.

Key design choice: Claude does NOT do the math. We hand it the figures the
engine already computed and ask it to *explain and recommend* — the part
language models are genuinely good at. This keeps the numbers auditable and
the narrative high quality.
"""

import os

from .engine import MonteCarloResults, PlanResults, Scenario
from .models import ClientProfile

# Note: `anthropic` and `python-dotenv` are imported lazily inside draft_plan()
# (not at module top) so the math-only path — e.g. `cli --no-ai` — runs with no
# AI dependencies installed at all.

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """\
You are a financial planning assistant working for a Registered Investment \
Advisor (RIA). You draft the first version of a retirement plan that a human \
advisor will review, edit, and deliver. You are not the advisor of record.

Write for the advisor, not the end client. Be concrete, organized, and \
practical. Ground every statement in the figures provided — never invent \
numbers, and never recompute them; if a figure isn't given, say so.

Structure the draft with these sections:
1. Situation summary (2-3 sentences)
2. Are they on track? (state it plainly; cite the accumulation surplus/gap AND \
the Monte Carlo probability, and explain what that probability means)
3. Recommendations (specific, prioritized, tied to the numbers — including the \
strategy levers below where they help)
4. Risks & assumptions to revisit with the client
5. Suggested next steps for the advisor

Keep a professional, plain-English tone. Flag anything that looks off (e.g. \
an aggressive return assumption) so the advisor can sanity-check it.

The Monte Carlo probability is a FULL-LIFECYCLE figure: the share of simulated \
lifetimes in which the portfolio lasts through retirement to life expectancy \
without running out (it models spending down, not just reaching a target). \
The brief also quantifies three method levers — a glide path (de-risking the \
allocation near retirement), flexible/dynamic spending (guardrails that trim \
withdrawals in down markets), and Social Security claiming age. When you \
recommend flexible spending, note honestly that its higher success rate comes \
partly from spending less in bad years.

The brief accounts for guaranteed income (Social Security, pensions, other), \
investment fees (returns are net of fees), the household's combined assets and \
income, the dynamic-withdrawal and glide-path methods, Social Security timing \
(including the bridge years before benefits begin), long-term care costs, and \
pre-Medicare healthcare costs — so don't describe these as absent from the \
model. The model also now captures contribution growth, a retirement spending decline \
(the "smile"), lognormal returns, and an explicit retirement tax rate — don't \
call those missing either. But several things are still modeled SIMPLY, and a \
good advisor draft is transparent about that rather than presenting the output \
as settled. In section 4, briefly name the simplifications that materially \
affect the result, including at least: taxes use one flat rate on portfolio \
withdrawals (no account-location, RMDs, Social Security taxation, or brackets); \
returns use fixed long-run mean/volatility (no regime shifts or fat tails); and \
the spending decline is a simple yearly taper. Frame the figures as a \
reasonable model to pressure-test with the client, not as precise predictions. \
Treat "validate assumptions with the client" as normal professional diligence.

Compliance note: include a short reminder that this is a draft for advisor \
review and not final investment advice."""


def _build_brief(
    profile: ClientProfile,
    results: PlanResults,
    mc: MonteCarloResults,
    scenario_list: list,
    strategy_list: list,
    claiming_list: list,
) -> str:
    """Format the profile + computed results into a clean brief for Claude."""
    status = "ON TRACK" if results.on_track else "SHORTFALL"
    if profile.retirement_expenses:
        items = "; ".join(f"{k} ${v:,.0f}" for k, v in profile.retirement_expenses.items())
        spending_line = (
            f"Retirement spending: client's itemized budget "
            f"${sum(profile.retirement_expenses.values()):,.0f}/yr ({items})"
        )
    else:
        spending_line = (
            f"Income replacement target: {profile.income_replacement_ratio:.0%} of income "
            f"(top-down estimate; the client did not itemize a budget)"
        )
    scenario_lines = "\n".join(
        f"    {s.label}: {s.probability_of_success:.0%}"
        for s in scenario_list
    )
    strategy_lines = "\n".join(
        f"    {s.label}: {s.probability_of_success:.0%}"
        for s in strategy_list
    )
    claiming_lines = "\n".join(
        f"    Claim at {c.claim_age}: ${c.annual_benefit:,.0f}/yr combined"
        f" -> {c.probability_of_success:.0%} success"
        for c in claiming_list
    )
    return f"""\
CLIENT PROFILE (all dollar figures are HOUSEHOLD totals, both spouses)
  Name: {profile.name}
  Age: {profile.current_age}, retiring at {profile.retirement_age} \
({results.years_to_retirement} years away), planning to age {profile.life_expectancy}
  Annual household income: ${profile.annual_income:,.0f}
  Current retirement savings (combined): ${profile.current_savings:,.0f}
  Monthly contribution (combined): ${profile.monthly_contribution:,.0f}, \
growing {profile.contribution_growth:.1%}/yr
  Risk tolerance: {profile.risk_tolerance}
  Advisor notes: {profile.notes or "(none)"}

GUARANTEED RETIREMENT INCOME (today's $, household — reduces portfolio need)
  Social Security (combined): ${profile.social_security_annual:,.0f}/yr
  Pension: ${profile.pension_annual:,.0f}/yr
  Other (rental, part-time, annuity): \
${profile.other_retirement_income_annual:,.0f}/yr

MAJOR COST PROVISIONS (today's $, modeled in the lifecycle simulation)
  Long-term care: ${profile.ltc_annual_cost:,.0f}/yr for the final \
{profile.ltc_years} years of the plan
  Pre-Medicare healthcare: ${profile.pre_medicare_annual_cost:,.0f}/yr while \
retired before age 65 ($0 if retiring at 65+)

PLANNING ASSUMPTIONS
  Expected return (before fees): {profile.expected_return:.1%}
  Investment fees: {profile.annual_fee:.1%}  ->  net return used: \
{results.net_return:.1%}
  Inflation: {profile.inflation:.1%}
  {spending_line}
  Retirement spending decline: {profile.retirement_spending_decline:.1%}/yr real \
(the "smile" — active years taper, healthcare/LTC added at the end)
  Retirement tax rate on portfolio withdrawals: {profile.retirement_tax_rate:.0%}
  Withdrawal rate: {profile.withdrawal_rate:.1%}
  Returns are modeled lognormally (random each year), not a fixed rate.

COMPUTED PROJECTIONS (already calculated — do not recompute)
  Projected nest egg at retirement: ${results.projected_nest_egg:,.0f}
  Total income needed (first retirement year): ${results.gross_income_need:,.0f}
  Covered by guaranteed income: ${results.guaranteed_income:,.0f}
  Left for the PORTFOLIO to provide: ${results.portfolio_income_need:,.0f}
  Nest egg required for that portfolio income: ${results.target_nest_egg:,.0f}
  Surplus / (gap): ${results.surplus_or_gap:,.0f}
  Status: {status}
  Total income the plan actually supports (portfolio + guaranteed): \
${results.sustainable_total_income:,.0f}/yr
  Monthly contribution required to hit target: \
${results.required_monthly_contribution:,.0f}
  Additional monthly savings needed beyond current: \
${results.additional_monthly_needed:,.0f}

MONTE CARLO — FULL LIFECYCLE ({mc.n_simulations:,} simulated lifetimes, do not recompute)
  Probability the money lasts to age {profile.life_expectancy}: {mc.probability_of_success:.0%}
  Starting return volatility: {mc.volatility:.0%}/yr (from risk tolerance)
  Nest-egg outcome range at retirement:
    Unlucky (10th pct): ${mc.p10:,.0f}
    Typical (median):   ${mc.p50:,.0f}
    Lucky   (90th pct): ${mc.p90:,.0f}

WHAT-IF SCENARIOS — savings/timing levers (probability money lasts, do not recompute)
{scenario_lines}

STRATEGY COMPARISON — method levers (probability money lasts, do not recompute)
{strategy_lines}

SOCIAL SECURITY TIMING (combined household benefit + success, do not recompute)
{claiming_lines}
"""


def draft_plan(
    profile: ClientProfile,
    results: PlanResults,
    mc: MonteCarloResults,
    scenario_list: list,
    strategy_list: list,
    claiming_list: list,
) -> str:
    """Call Claude to write the plan. Requires ANTHROPIC_API_KEY in the env."""
    import anthropic            # imported here so the math path needs no AI deps
    from dotenv import load_dotenv

    load_dotenv()              # pick up ANTHROPIC_API_KEY from a local .env file
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Open .env and paste your key, "
            "or run: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.Anthropic()
    brief = _build_brief(
        profile, results, mc, scenario_list, strategy_list, claiming_list
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Draft a retirement plan from this brief.\n\n" + brief
                ),
            }
        ],
    )

    # The response can include thinking blocks; we only want the text the
    # model wrote for the advisor.
    return "".join(
        block.text for block in response.content if block.type == "text"
    )
