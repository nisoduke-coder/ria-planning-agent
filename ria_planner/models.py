"""The client's financial picture, in one place.

A dataclass is just a tidy container for related values. Every field below is
something an advisor would collect during intake. Defaults reflect common
planning assumptions so you can leave most of them alone while testing.
"""

from dataclasses import dataclass


@dataclass
class ClientProfile:
    # --- Who they are ---
    name: str
    current_age: int
    retirement_age: int
    life_expectancy: int = 92          # plan to age 92 so we don't underplan

    # --- Cash flow & assets (today's dollars; HOUSEHOLD totals, both spouses) ---
    annual_income: float = 0.0         # gross household income
    current_savings: float = 0.0       # all invested retirement assets, both spouses
    monthly_contribution: float = 0.0  # combined household retirement saving / month

    # --- Guaranteed retirement income (today's dollars, household) ---
    # Income that does NOT come from the portfolio, so it lowers how big the
    # nest egg must be. Estimate Social Security from ssa.gov statements.
    # Use the full-retirement-age (67) estimate; the engine can model claiming
    # earlier or later from this baseline.
    social_security_annual: float = 0.0          # combined SS benefit at age 67
    pension_annual: float = 0.0                  # employer / government pensions
    other_retirement_income_annual: float = 0.0  # rental, part-time, annuity, etc.

    # --- Major retirement cost provisions (today's dollars) ---
    # Extra costs the base replacement target doesn't capture.
    ltc_annual_cost: float = 0.0          # long-term care, applied at end of plan
    ltc_years: int = 3                    # how many end-of-life years LTC lasts
    pre_medicare_annual_cost: float = 0.0  # extra healthcare/yr if retiring before 65

    # --- Planning assumptions ---
    expected_return: float = 0.06      # nominal annual portfolio return, before fees
    annual_fee: float = 0.01           # advisory + fund fees (1%); reduces net return
    inflation: float = 0.025           # annual inflation (2.5%)
    income_replacement_ratio: float = 0.75  # % of gross income needed (pre-tax)
    withdrawal_rate: float = 0.04      # sustainable withdrawal rate (the "4% rule")

    # --- Context for the advisor narrative ---
    risk_tolerance: str = "moderate"   # conservative | moderate | aggressive
    notes: str = ""                    # anything else worth telling the planner

    @property
    def net_return(self) -> float:
        """Expected return after advisory and fund fees come out."""
        return self.expected_return - self.annual_fee

    # (MeetingContext is defined at the bottom of this file.)

    @property
    def years_to_retirement(self) -> int:
        return max(self.retirement_age - self.current_age, 0)

    @property
    def years_in_retirement(self) -> int:
        return max(self.life_expectancy - self.retirement_age, 0)


@dataclass
class MeetingContext:
    """Optional context for a specific upcoming meeting (all free text)."""

    purpose: str = "Portfolio review"   # why you're meeting
    last_review: str = ""               # when you last met, e.g. "June 2025"
    open_items: str = ""                # outstanding action items from last time
    notes: str = ""                     # anything else relevant to this meeting
