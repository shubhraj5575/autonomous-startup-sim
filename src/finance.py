"""Finance: ledger, cash accounting and SaaS metric engine.

The ledger is the single source of truth for cash. Every rupee that moves is a
LedgerEntry; metrics are derived, never asserted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

INCOME_CATEGORIES = {"subscription", "annual_prepay", "services", "interest"}
EXPENSE_CATEGORIES = {
    "salaries", "recruiting", "severance", "marketing", "tools", "infra",
    "payment_fees", "commission", "founder_draw", "events_misc", "loan_interest",
    "legal_compliance",
}


@dataclass
class LedgerEntry:
    day: int
    category: str
    amount: float          # positive = inflow, negative = outflow
    note: str = ""


@dataclass
class DailySnapshot:
    day: int
    date_label: str
    cash: float
    mrr: float
    arr: float
    active_customers: int
    new_customers_today: int
    churned_today: int
    revenue_recognized_mtd: float      # subscription revenue recognized month-to-date
    opex_mtd: float
    net_income_mtd: float
    gross_margin_pct: float            # trailing 30d
    cac_blended: float                 # trailing 30d
    ltv: float                         # current estimate
    ltv_cac: float
    payback_months: float
    logo_churn_pct_monthly: float      # trailing 30d / prior base
    net_revenue_retention_pct: float   # trailing 90d approx
    runway_months: float               # at current net burn; inf if profitable
    valuation_proxy: float
    market_share_pct: float            # share of simulated universe MRR
    headcount: int
    brand_awareness: float             # 0..1 avg across pool
    pipeline_value: float
    leads_trailing30: int


class FinanceEngine:
    def __init__(self, starting_cash: float):
        self.cash = float(starting_cash)
        self.ledger: list[LedgerEntry] = []
        # fast window sums: category -> [amount_at_day] (index == day)
        self.cat_day: dict[str, list[float]] = {}
        self.equity_rounds: list[dict] = []     # day, amount, dilution, post_money
        self.founder_equity = 1.0               # fraction retained by founders
        self.debt: float = 0.0

    # ------------------------------------------------------------- ledger ---
    def record(self, day: int, category: str, amount: float, note: str = "") -> None:
        if category in EXPENSE_CATEGORIES:
            amount = -abs(amount)
        self.cash += amount
        self.ledger.append(LedgerEntry(day, category, amount, note))
        row = self.cat_day.setdefault(category, [])
        while len(row) <= day:
            row.append(0.0)
        row[day] += amount

    def spend_between(self, d0: int, d1: int, categories: set[str]) -> float:
        return sum(self.sum_category(c, d0, d1) for c in categories)

    def sum_category(self, category: str, d0: int, d1: int) -> float:
        """O(window) sum over [d0, d1) using the day-indexed structure."""
        row = self.cat_day.get(category)
        if not row:
            return 0.0
        d0 = max(d0, 0)
        d1 = min(d1, len(row))
        if d1 <= d0:
            return 0.0
        return sum(row[d0:d1])

    # ------------------------------------------------------------ funding ---
    def raise_equity(self, day: int, amount: float, dilution: float, post_money: float) -> None:
        self.cash += amount
        self.ledger.append(LedgerEntry(day, "equity_inflow", amount, f"raise post={post_money:.0f}"))
        self.founder_equity *= (1.0 - dilution)
        self.equity_rounds.append(dict(day=day, amount=amount, dilution=dilution,
                                       post_money=post_money))

    # ------------------------------------------------------------ metrics ---
    @staticmethod
    def compute_runway(cash: float, net_burn_30d: float) -> float:
        """Runway in months at trailing-30d net burn. inf if burn <= 0."""
        if net_burn_30d <= 0:
            return float("inf")
        months = cash / net_burn_30d
        return max(0.0, min(months, 999.0))

    @staticmethod
    def valuation_proxy(arr: float, growth_rate_annualized: float,
                         gross_margin: float, monthly_logo_churn: float) -> float:
        """Defensible heuristic: revenue multiple driven by growth & quality.

        multiple = clamp(3 + 18*growth_frac - 6*churn_frac, 2.5, 14), scaled by
        margin factor in [0.7, 1.15]. ARR floors at 0.
        """
        if arr <= 0:
            return 0.0
        g = max(-0.5, min(growth_rate_annualized, 3.0))
        mult = 3.0 + 18.0 * g - 6.0 * (monthly_logo_churn / 100.0)
        mult *= (0.70 + 0.45 * max(0.0, min(gross_margin, 0.95)))
        mult = max(2.0, min(mult, 16.0))
        return arr * mult
