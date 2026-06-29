"""Portfolio analysis: current allocation vs. target, drift, and rebalancing.

Pure deterministic math (no AI) — same principle as the planning engine: the
numbers must be auditable. The AI layer (portfolio_agent.py) writes the
advisor-facing commentary on top of these figures.

Everything is illustrative; the target allocations are simple model portfolios
tied to risk tolerance, not personalized investment advice.
"""

from dataclasses import dataclass

from .models import Holding

# Target allocation (% of portfolio) by risk tolerance. Each row sums to 100.
# Illustrative model allocations — a real firm would use its own.
TARGET_ALLOCATIONS = {
    "conservative": {"equity": 30, "fixed_income": 50, "cash": 15, "real_estate": 5},
    "moderate":     {"equity": 60, "fixed_income": 30, "cash": 5,  "real_estate": 5},
    "aggressive":   {"equity": 85, "fixed_income": 10, "cash": 0,  "real_estate": 5},
}
DEFAULT_RISK = "moderate"

# An asset class this many percentage points off target gets flagged.
DRIFT_THRESHOLD = 5.0
# A single holding above this share of the portfolio is a concentration flag.
CONCENTRATION_THRESHOLD = 25.0

ASSET_CLASS_LABELS = {
    "equity": "Equities (stocks)",
    "fixed_income": "Fixed income (bonds)",
    "cash": "Cash",
    "real_estate": "Real estate",
    "other": "Other / alternatives",
}


@dataclass
class PortfolioAnalysis:
    total_value: float
    classes: list          # asset classes, in a stable display order
    current_pct: dict      # class -> current % of portfolio
    target_pct: dict       # class -> target % for this risk level
    drift: dict            # class -> percentage points off (current - target)
    rebalancing: dict      # class -> $ to buy (+) or sell (-) to hit target
    largest_name: str
    largest_value: float
    largest_pct: float
    needs_rebalancing: bool
    flags: list            # plain-English issues worth the advisor's attention


def analyze_portfolio(holdings, risk_tolerance=DEFAULT_RISK) -> PortfolioAnalysis:
    """Compare a set of holdings to the target model for a risk level."""
    total = sum(h.value for h in holdings)
    if total <= 0:
        raise ValueError("Portfolio total must be positive.")

    target = TARGET_ALLOCATIONS.get(risk_tolerance, TARGET_ALLOCATIONS[DEFAULT_RISK])

    # Sum each holding's value into its asset class.
    by_class = {}
    for h in holdings:
        by_class[h.asset_class] = by_class.get(h.asset_class, 0.0) + h.value

    # Show every class in the target, plus any extra ones the holdings use.
    classes = list(target.keys())
    for c in by_class:
        if c not in classes:
            classes.append(c)

    current_pct, target_pct, drift, rebalancing = {}, {}, {}, {}
    for c in classes:
        cur_val = by_class.get(c, 0.0)
        current_pct[c] = cur_val / total * 100
        target_pct[c] = float(target.get(c, 0))
        drift[c] = current_pct[c] - target_pct[c]
        # Positive = buy this much to reach target; negative = sell.
        rebalancing[c] = total * target_pct[c] / 100 - cur_val

    largest = max(holdings, key=lambda h: h.value)
    largest_pct = largest.value / total * 100

    flags = []
    for c in classes:
        label = ASSET_CLASS_LABELS.get(c, c)
        if drift[c] > DRIFT_THRESHOLD:
            flags.append(f"Overweight {label} by {drift[c]:.0f} points")
        elif drift[c] < -DRIFT_THRESHOLD:
            flags.append(f"Underweight {label} by {abs(drift[c]):.0f} points")
    if largest_pct > CONCENTRATION_THRESHOLD:
        flags.append(
            f"Concentration risk: {largest.name} is {largest_pct:.0f}% of the portfolio"
        )
    for c in by_class:
        if c not in target:
            flags.append(
                f"'{c}' isn't in the target model — classify it or set a target weight"
            )

    return PortfolioAnalysis(
        total_value=total,
        classes=classes,
        current_pct=current_pct,
        target_pct=target_pct,
        drift=drift,
        rebalancing=rebalancing,
        largest_name=largest.name,
        largest_value=largest.value,
        largest_pct=largest_pct,
        needs_rebalancing=any(abs(drift[c]) > DRIFT_THRESHOLD for c in classes),
        flags=flags,
    )
