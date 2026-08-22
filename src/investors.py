"""Investor market: term sheets appear when traction is real.

Sheets are priced off the same valuation logic the finance engine uses (with a
negotiation spread), so fundraising is genuinely coupled to performance.
"""
from __future__ import annotations

import random

from .rng import clamp
from .finance import FinanceEngine


FIRMS = ["Indus Ventures", "Bharat Seed Fund", "Mumbai Angels X", "Pebble Capital",
         "Deccan Growth Partners", "Nucleus Capital"]


def maybe_term_sheet(company, view, rng: random.Random) -> dict | None:
    """Called monthly. Returns a sheet dict or None; CEO decides."""
    c = company
    k_mrr = c.current_mrr
    if k_mrr < 40_000:
        return None
    h = c.history
    growth = 0.0
    if len(h) >= 90 and h[-90]["mrr"] > 0:
        arr0, arr1 = h[-90]["mrr"] * 12, c.current_mrr * 12
        growth = (arr1 / arr0 - 1)
    strong_growth = growth > 0.9          # ~tripled ARR in trailing quarter-year window
    big_arr = k_mrr * 12 > 2_500_000
    decent_churn = (h[-1]["logo_churn_pct_monthly"] if h else 20) < 12
    margin_ok = (h[-1]["gross_margin_pct"] if h else 0.5) > 0.35
    if not ((strong_growth or big_arr) and decent_churn and margin_ok):
        return None

    arr = k_mrr * 12
    gm = h[-1]["gross_margin_pct"]
    churn = (h[-1]["logo_churn_pct_monthly"]) / 100.0
    base_val = FinanceEngine.valuation_proxy(arr, max(growth, 0.15), gm, churn * 100)
    post = base_val * rng.uniform(0.85, 1.05)
    amount = clamp(post * rng.uniform(0.16, 0.24), 300_000, 60_000_000)
    dilution = min(0.28, amount / post)
    return dict(firm=rng.choice(FIRMS), amount=round(amount, -3),
                post_money=round(post, -4), dilution=round(dilution, 4),
                note="2 board seats; standard 1x liquidation preference.")
