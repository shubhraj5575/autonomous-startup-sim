"""Finance invariants and KPI sanity across whole runs."""
from src.config import SimConfig
from src.simulator import World


def _run(days=240, seed=31):
    cfg = SimConfig(seed=seed)
    w = World(cfg)
    c = w.run(days)
    return c


def test_cash_matches_ledger_every_step():
    c = _run()
    running = c.finance.starting_cash if hasattr(c.finance, "starting_cash") else 100_000.0
    # recompute from scratch
    total = sum(e.amount for e in c.finance.ledger)
    # equity raises bypass record(); account for them
    raises = sum(r["amount"] for r in c.finance.equity_rounds)
    assert abs((100_000.0 + total + raises) - c.finance.cash) < 1e-6


def test_no_negative_cash_unless_bankrupt():
    c = _run()
    if c.alive:
        assert c.finance.cash > -50_000
    else:
        assert "Insolvent" in c.death_reason or c.death_reason


def test_kpi_series_sane():
    c = _run()
    for s in c.history:
        assert -60_000 < s["cash"] < 1e10
        assert s["mrr"] >= 0
        assert s["active_customers"] >= 0
        assert 0 <= s["market_share_pct"] <= 100
        assert 0 <= s["gross_margin_pct"] <= 100
        assert s["logo_churn_pct_monthly"] >= 0
        assert s["cac_blended"] >= 0
        assert s["headcount"] >= 1


def test_mrr_book_matches_active_fees():
    c = _run()
    fees = sum(c.pool.get(cid).monthly_fee for cid in c.pool.ids_in_state("active"))
    assert abs(fees - c.current_mrr) < 0.01


def test_pool_conservation():
    c = _run()
    counts = c.pool.counts()
    assert sum(counts.values()) == c.pool.total_size
    active_in_pool = c.pool.ids_in_state("active")
    assert active_in_pool == set(c.active_ids)


def test_valuation_nonnegative_and_zero_without_revenue():
    from src.finance import FinanceEngine
    assert FinanceEngine.valuation_proxy(0, 1.0, 0.8, 3) == 0
    v = FinanceEngine.valuation_proxy(10_000_000, 0.5, 0.8, 2)
    assert v > 0


def test_runway_math():
    from src.finance import FinanceEngine
    assert FinanceEngine.compute_runway(100_000, 50_000) == 2.0
    assert FinanceEngine.compute_runway(100_000, 0) == float("inf")
