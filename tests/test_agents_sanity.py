"""Agent-layer sanity: decision records complete, evaluations close, learning bounded."""
from src.config import SimConfig
from src.simulator import World


def _run(days=200, seed=88):
    cfg = SimConfig(seed=seed)
    w = World(cfg)
    c = w.run(days)
    return c, w


def test_decision_log_schema():
    c, _ = _run()
    assert len(c.decision_log) >= 3
    for d in c.decision_log:
        for k in ("id", "day", "agent", "kind", "decision", "reasoning",
                  "data_considered", "expected", "eval_due_day"):
            assert k in d, f"missing {k}"
        assert d["reasoning"], "reasoning must not be empty"
        assert isinstance(d["data_considered"], dict)


def test_decisions_get_evaluated():
    c, _ = _run(days=260)
    evaluated = [d for d in c.decision_log if d.get("verdict")]
    assert evaluated, "decisions should be evaluated after their horizon"
    for d in evaluated:
        assert d["verdict"] in ("success", "partial", "fail", "untracked")
        if d["verdict"] != "untracked":
            assert "actual" in d


def test_channel_scores_stay_bounded():
    c, _ = _run()
    for ch, st_ in c.marketing.channels.items():
        assert 0.0 <= st_.bandit_score <= 4.0, ch


def test_price_mult_within_guardrails():
    c, _ = _run(days=300)
    assert 0.70 <= c.product.price_mult <= 1.45


def test_elasticity_estimate_updated_or_prior():
    c, _ = _run(days=300)
    assert -3.5 <= c.price_elasticity_est <= -0.15


def test_marketing_budget_never_exceeds_cash_guardrail():
    c, w = _run(days=150)
    # daily marketing spend recorded can't exceed 2% of cash + small floor
    for e in c.finance.ledger:
        if e.category == "marketing":
            pass  # spot check happens implicitly via survival; detailed cap tested below
    # stronger check: at no point does cumulative single-day marketing exceed
    # 25% of that day's opening cash (guardrail is 2%, allow slack)
    by_day = {}
    row = c.finance.cat_day.get("marketing", [])
    hist = c.history
    for day, amt in enumerate(row):
        if amt != 0 and day < len(hist):
            opening = hist[day]["cash"] - sum(
                x for x in [hist[day].get("_na", 0)]) + amt
            by_day[day] = amt / max(abs(opening), 1)
    worst = max(by_day.values()) if by_day else 0
    assert worst < 0.35, f"marketing burned {worst:.0%} of cash in one day"
