"""AI layer for portfolio analysis: Claude writes the advisor commentary.

Same split as the planning side — the math (allocation, drift, rebalancing
dollars) is computed in portfolio.py; here Claude explains it and recommends,
without recomputing the numbers.
"""

import os

from .agent import MODEL
from .portfolio import ASSET_CLASS_LABELS, PortfolioAnalysis

PORTFOLIO_SYSTEM_PROMPT = """\
You are a financial planning assistant for a Registered Investment Advisor \
(RIA). Write an advisor-facing portfolio analysis from the computed figures. \
You draft; a human advisor reviews, edits, and delivers.

Ground every statement in the numbers provided — never invent or recompute \
them. Structure the analysis:

1. Snapshot — total value and, in one or two lines, how the current allocation \
compares to the target for this risk level.
2. Allocation drift — which asset classes are off target and by how much, in \
plain terms (overweight/underweight, and why that matters).
3. Rebalancing recommendations — the specific buy/sell dollar amounts to bring \
each class back to target. Add a practical caveat that the advisor should apply \
tax-awareness (sell in tax-advantaged accounts first; watch capital gains in \
taxable accounts) and trading-cost/practicality judgment — the model doesn't.
4. Risks to flag — concentration in a single holding, cash drag, or anything \
that stands out.
5. Suggested next steps for the advisor.

Keep a professional, plain-English tone. The target allocation is a simple \
model tied to the stated risk tolerance, not personalized advice — say so. End \
with a short note that this is a draft for advisor review, not final investment \
advice."""


def _money(x):
    return f"${x:,.0f}"


def _build_portfolio_brief(holdings, analysis: PortfolioAnalysis, risk: str) -> str:
    lines = [
        f"PORTFOLIO ({len(holdings)} holdings, total {_money(analysis.total_value)})",
        f"Target model: {risk} risk tolerance",
        "",
        "ALLOCATION (do not recompute):",
        "  class | current% | target% | drift(pts) | rebalance $",
    ]
    for c in analysis.classes:
        label = ASSET_CLASS_LABELS.get(c, c)
        trade = analysis.rebalancing[c]
        action = f"buy {_money(trade)}" if trade >= 0 else f"sell {_money(-trade)}"
        lines.append(
            f"  {label}: {analysis.current_pct[c]:.0f}% | {analysis.target_pct[c]:.0f}% | "
            f"{analysis.drift[c]:+.0f} | {action}"
        )
    lines += [
        "",
        f"Largest holding: {analysis.largest_name} "
        f"({_money(analysis.largest_value)}, {analysis.largest_pct:.0f}% of portfolio)",
        "",
        "FLAGS:",
    ]
    lines += [f"  - {f}" for f in analysis.flags] or ["  (none)"]
    lines += ["", "HOLDINGS:"]
    for h in holdings:
        label = ASSET_CLASS_LABELS.get(h.asset_class, h.asset_class)
        lines.append(f"  {h.name}: {_money(h.value)} ({label})")
    return "\n".join(lines)


def portfolio_commentary(holdings, analysis: PortfolioAnalysis, risk: str) -> str:
    """Call Claude to write the portfolio analysis. Requires ANTHROPIC_API_KEY."""
    import anthropic
    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Open .env and paste your key, "
            "or run: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.Anthropic()
    brief = _build_portfolio_brief(holdings, analysis, risk)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=PORTFOLIO_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": "Analyze this portfolio.\n\n" + brief}
        ],
    )
    return "".join(b.text for b in response.content if b.type == "text")
