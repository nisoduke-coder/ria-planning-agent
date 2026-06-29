"""Run the planner end to end.

    # built-in sample client
    python -m ria_planner.cli
    python -m ria_planner.cli --no-ai            # math only, no API key

    # load a real client from a file
    python -m ria_planner.cli --client clients/dana.json
    python -m ria_planner.cli --clients-csv clients/book.csv   # whole book

    # save the plan as a deliverable Markdown file (in output/)
    python -m ria_planner.cli --client clients/dana.json --save

    # prep for a client meeting (cheat-sheet instead of a full plan)
    python -m ria_planner.cli --client clients/dana.json --meeting
    python -m ria_planner.cli --client clients/dana.json --meeting \
        --purpose "Annual review" --since "June 2025" --save
"""

import argparse

from .agent import draft_plan
from .engine import (
    MonteCarloResults,
    PlanResults,
    claiming_comparison,
    monte_carlo,
    run_plan,
    scenarios,
    strategy_comparison,
)
from .intake import (
    load_client_json,
    load_clients_csv,
    load_meeting_context_json,
)
from .meeting import prep_meeting
from .models import ClientProfile, MeetingContext
from .report import build_markdown, save_report

DISCLAIMER = (
    "ILLUSTRATIVE ONLY. Projections use simplified assumptions and are a draft "
    "for advisor review — not investment advice or a guarantee of results."
)

# A realistic sample so you see output immediately. Swap in real intake data.
SAMPLE_CLIENT = ClientProfile(
    name="Dana Whitfield",
    current_age=48,
    retirement_age=67,
    annual_income=160_000,
    current_savings=720_000,
    monthly_contribution=3_500,
    social_security_annual=48_000,   # combined est. for both spouses (~$24k each)
    ltc_annual_cost=70_000,          # ~3 years of care at end of life
    ltc_years=3,
    pre_medicare_annual_cost=0,      # retires at 67, so no pre-Medicare gap
    expected_return=0.065,
    annual_fee=0.01,
    income_replacement_ratio=0.70,
    risk_tolerance="aggressive",
    notes="Married, dual income, kids' college already funded. Strong saver.",
)


def _money(x: float) -> str:
    return f"${x:,.0f}"


def print_numbers(profile: ClientProfile, r: PlanResults) -> None:
    print("=" * 64)
    print(f"  RETIREMENT PROJECTION — {profile.name}")
    print("=" * 64)
    print(f"  Years to retirement:        {r.years_to_retirement}")
    print(f"  Net return (after fees):    {r.net_return:.1%}")
    print(f"  Projected nest egg:         {_money(r.projected_nest_egg)}")
    print(f"  Target nest egg:            {_money(r.target_nest_egg)}")
    print("-" * 64)
    print(f"  Total income needed (yr 1): {_money(r.gross_income_need)}/yr")
    print(f"   - guaranteed income:       {_money(r.guaranteed_income)}/yr")
    print(f"   = portfolio must provide:  {_money(r.portfolio_income_need)}/yr")
    print(f"  Plan actually supports:     {_money(r.sustainable_total_income)}/yr")
    print("-" * 64)
    ltc = (
        f"{_money(profile.ltc_annual_cost)}/yr x {profile.ltc_years}yrs"
        if profile.ltc_annual_cost > 0
        else "not modeled"
    )
    bridge = (
        f"{_money(profile.pre_medicare_annual_cost)}/yr (pre-65)"
        if profile.pre_medicare_annual_cost > 0
        else "n/a (retires at 65+)"
    )
    print(f"  Long-term care provision:   {ltc}")
    print(f"  Pre-Medicare healthcare:    {bridge}")
    print("-" * 64)
    if r.on_track:
        print(f"  STATUS: ON TRACK — surplus of {_money(r.surplus_or_gap)}")
    else:
        print(f"  STATUS: SHORTFALL of {_money(-r.surplus_or_gap)}")
        print(f"  Save {_money(r.additional_monthly_needed)}/mo more to close it")
        print(f"  (total {_money(r.required_monthly_contribution)}/mo)")
    print("=" * 64)


def print_monte_carlo(profile: ClientProfile, mc: MonteCarloResults) -> None:
    print()
    print("=" * 64)
    print(f"  MONTE CARLO — {mc.n_simulations:,} simulated lifetimes")
    print("=" * 64)
    pct = mc.probability_of_success * 100
    print(f"  Probability money lasts to age {profile.life_expectancy}:  {pct:.0f}%")
    print(f"  (starting return volatility: {mc.volatility:.0%}/yr)")
    print("-" * 64)
    print("  Range of nest-egg outcomes at retirement:")
    print(f"    Unlucky  (10th pct):  {_money(mc.p10)}")
    print(f"    Typical  (median):    {_money(mc.p50)}")
    print(f"    Lucky    (90th pct):  {_money(mc.p90)}")
    print("=" * 64)


def print_scenarios(scenario_list: list) -> None:
    print()
    print("=" * 64)
    print("  WHAT-IF SCENARIOS — probability of success per lever")
    print("=" * 64)
    for s in scenario_list:
        print(f"  {s.label:<34} {s.probability_of_success * 100:>3.0f}%")
    print("=" * 64)


def print_strategy(strategy_list: list) -> None:
    print()
    print("=" * 64)
    print("  STRATEGY COMPARISON — glide path & flexible spending")
    print("=" * 64)
    for s in strategy_list:
        print(f"  {s.label:<40} {s.probability_of_success * 100:>3.0f}%")
    print("=" * 64)


def print_claiming(claiming_list: list) -> None:
    print()
    print("=" * 64)
    print("  SOCIAL SECURITY TIMING — claim age vs. success")
    print("=" * 64)
    for c in claiming_list:
        print(
            f"  Claim at {c.claim_age}:  {_money(c.annual_benefit)}/yr combined"
            f"   ->  {c.probability_of_success * 100:>3.0f}% success"
        )
    print("=" * 64)


def _load_profiles(args) -> list:
    """Decide which client(s) to run, from a file or the built-in sample."""
    if args.client:
        return [load_client_json(args.client)]
    if args.clients_csv:
        return load_clients_csv(args.clients_csv)
    return [SAMPLE_CLIENT]


def process_client(profile: ClientProfile, args, meeting_context=None) -> None:
    """Run the full pipeline for one client: compute, print, draft, save."""
    results = run_plan(profile)
    mc = monte_carlo(profile)
    scenario_list = scenarios(profile)
    strategy_list = strategy_comparison(profile)
    claiming_list = claiming_comparison(profile)

    print_numbers(profile, results)
    print_monte_carlo(profile, mc)
    print_scenarios(scenario_list)
    print_strategy(strategy_list)
    print_claiming(claiming_list)

    text = None
    if args.no_ai:
        print("\n[--no-ai] Skipping AI output.")
    else:
        label = "pre-meeting briefing" if args.meeting else "advisor-facing plan"
        print(f"\nGenerating {label} with Claude...\n")
        try:
            if args.meeting:
                text = prep_meeting(
                    profile, results, mc, scenario_list, strategy_list,
                    claiming_list, meeting_context or MeetingContext(),
                )
            else:
                text = draft_plan(
                    profile, results, mc, scenario_list, strategy_list, claiming_list
                )
            print(text)
        except RuntimeError as exc:
            print(f"Could not generate AI output: {exc}")
            print("Tip: run with --no-ai to see the numbers without a key.")

    if args.save:
        if args.meeting:
            markdown = build_markdown(
                profile, results, mc, scenario_list, strategy_list, claiming_list,
                text, heading="Pre-Meeting Briefing", draft_section="Briefing",
            )
            path = save_report(markdown, profile, args.out, suffix="-meeting")
        else:
            markdown = build_markdown(
                profile, results, mc, scenario_list, strategy_list, claiming_list, text
            )
            path = save_report(markdown, profile, args.out)
        print(f"\nSaved report -> {path}")

    print(f"\n{DISCLAIMER}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a retirement plan.")
    parser.add_argument(
        "--client", metavar="PATH", help="Load one client from a JSON file."
    )
    parser.add_argument(
        "--clients-csv",
        metavar="PATH",
        help="Load many clients from a CSV file (one row each).",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save the plan as a Markdown file in the output directory.",
    )
    parser.add_argument(
        "--out",
        metavar="DIR",
        default="output",
        help="Where to save reports (default: output/).",
    )
    parser.add_argument(
        "--meeting",
        action="store_true",
        help="Produce a pre-meeting briefing instead of a full plan.",
    )
    parser.add_argument("--purpose", help="Meeting purpose (e.g. 'Annual review').")
    parser.add_argument("--since", help="When you last met (e.g. 'June 2025').")
    parser.add_argument("--open-items", help="Outstanding action items from last time.")
    parser.add_argument("--notes", help="Any notes for this specific meeting.")
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip the Claude output; show the math only (no API key needed).",
    )
    args = parser.parse_args()

    try:
        profiles = _load_profiles(args)
    except (OSError, ValueError) as exc:
        print(f"Could not load client data: {exc}")
        return

    # Meeting context: start from the client file's optional "meeting" block,
    # then let command-line flags override any field.
    meeting_context = MeetingContext()
    if args.client:
        meeting_context = load_meeting_context_json(args.client)
    if args.purpose:
        meeting_context.purpose = args.purpose
    if args.since:
        meeting_context.last_review = args.since
    if args.open_items:
        meeting_context.open_items = args.open_items
    if args.notes:
        meeting_context.notes = args.notes

    for i, profile in enumerate(profiles):
        if i > 0:
            print("\n\n")  # space between clients in a batch
        process_client(profile, args, meeting_context)


if __name__ == "__main__":
    main()
