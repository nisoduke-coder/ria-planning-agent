"""Export a finished plan to a Markdown file an advisor could hand over.

Markdown opens anywhere, prints cleanly, and converts to PDF/Word easily. We
write the auditable numbers (as tables) followed by the AI-written narrative.
"""

import datetime
import os
import re

from .engine import MonteCarloResults, PlanResults
from .models import ClientProfile

DISCLAIMER = (
    "_Illustrative only. Projections use simplified assumptions and are a draft "
    "for advisor review — not investment advice or a guarantee of results._"
)


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _slug(name: str) -> str:
    """Turn 'Dana Whitfield' into 'dana-whitfield' for a safe filename."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "client"


def build_markdown(
    profile: ClientProfile,
    results: PlanResults,
    mc: MonteCarloResults,
    scenario_list: list,
    strategy_list: list,
    claiming_list: list,
    plan_text: str = None,
    heading: str = "Retirement Plan",
    draft_section: str = "Advisor draft",
) -> str:
    """Assemble the full report as one Markdown string."""
    today = datetime.date.today().isoformat()
    status = "On track" if results.on_track else "Shortfall"

    parts = [
        f"# {heading} — {profile.name}",
        f"_Prepared {today} · DRAFT for advisor review_",
        "",
        "## Key figures",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Years to retirement | {results.years_to_retirement} |",
        f"| Net return (after fees) | {results.net_return:.1%} |",
        f"| Projected nest egg | {_money(results.projected_nest_egg)} |",
        f"| Target nest egg | {_money(results.target_nest_egg)} |",
        f"| Total income needed (yr 1) | {_money(results.gross_income_need)}/yr |",
        f"| Guaranteed income | {_money(results.guaranteed_income)}/yr |",
        f"| Portfolio must provide | {_money(results.portfolio_income_need)}/yr |",
        f"| Accumulation status | {status} ({_money(results.surplus_or_gap)}) |",
        "",
        f"## Monte Carlo — probability money lasts to age {profile.life_expectancy}",
        "",
        f"**{mc.probability_of_success:.0%}** across {mc.n_simulations:,} "
        f"simulated lifetimes (starting volatility {mc.volatility:.0%}/yr).",
        "",
        "| Outcome at retirement | Nest egg |",
        "|---|---|",
        f"| Unlucky (10th pct) | {_money(mc.p10)} |",
        f"| Typical (median) | {_money(mc.p50)} |",
        f"| Lucky (90th pct) | {_money(mc.p90)} |",
        "",
        "## What-if scenarios (savings & timing)",
        "",
        "| Lever | Success |",
        "|---|---|",
    ]
    parts += [f"| {s.label} | {s.probability_of_success:.0%} |" for s in scenario_list]
    parts += [
        "",
        "## Strategy comparison (allocation & spending method)",
        "",
        "| Strategy | Success |",
        "|---|---|",
    ]
    parts += [f"| {s.label} | {s.probability_of_success:.0%} |" for s in strategy_list]
    parts += [
        "",
        "## Social Security timing",
        "",
        "| Claim age | Combined benefit | Success |",
        "|---|---|---|",
    ]
    parts += [
        f"| {c.claim_age} | {_money(c.annual_benefit)}/yr | {c.probability_of_success:.0%} |"
        for c in claiming_list
    ]

    parts += ["", f"## {draft_section}", ""]
    parts.append(plan_text.strip() if plan_text else "_(AI draft not generated.)_")

    parts += ["", "---", "", DISCLAIMER, ""]
    return "\n".join(parts)


def save_report(
    markdown: str, profile: ClientProfile, outdir: str = "output", suffix: str = ""
) -> str:
    """Write the Markdown report to outdir and return the file path."""
    os.makedirs(outdir, exist_ok=True)
    today = datetime.date.today().isoformat()
    path = os.path.join(outdir, f"{_slug(profile.name)}{suffix}-{today}.md")
    with open(path, "w") as f:
        f.write(markdown)
    return path
