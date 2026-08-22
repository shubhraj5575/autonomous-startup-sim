"""Customer model unit checks."""
from src.customers import Customer, Offer, evaluate_offer, choice_probability, fit_score


def _cust(needs, budget=3000, seg="d2c_brands"):
    return Customer(cid=1, segment=seg, budget=budget, needs=needs)


FTIERS = {"core_billing": 0, "inventory_basic": 0, "whatsapp_deep": 1,
          "payments_upi": 1, "orders_sync": 1, "analytics_dash": 1,
          "crm_lite": 1, "inventory_advanced": 2, "api_access": 2,
          "security_sso": 2, "sla_support": 3}


def test_fit_score_partial_coverage():
    c = _cust({"core_billing": 0.9, "inventory_basic": 0.75})
    f_all = fit_score(c, {"core_billing", "inventory_basic"})
    assert abs(f_all - 1.0) < 1e-9
    f_half = fit_score(c, {"core_billing"})
    assert 0.5 < f_half < 0.65


def test_higher_price_lower_utility():
    c = _cust({"core_billing": 0.9}, budget=2000)
    cheap = Offer("a", "A", {"core_billing"}, 0.6, 0.4, [499, 1999, 5999], 0.8)
    u_cheap, t1 = evaluate_offer(c, cheap, FTIERS)
    pricey = Offer("b", "B", {"core_billing"}, 0.6, 0.4, [1499, 1999, 5999], 0.8)
    u_pricey, t2 = evaluate_offer(c, pricey, FTIERS)
    assert u_cheap > u_pricey


def test_more_features_higher_utility():
    c = _cust({"core_billing": 0.9, "analytics_dash": 0.7}, budget=3000)
    bare = Offer("a", "A", {"core_billing"}, 0.6, 0.4, [499, 1999, 5999], 0.8)
    full = Offer("b", "B", {"core_billing", "analytics_dash"}, 0.6, 0.4,
                 [499, 1999, 5999], 0.8)
    assert evaluate_offer(c, full, FTIERS)[0] > evaluate_offer(c, bare, FTIERS)[0]


def test_choice_probability_monotone():
    lo = choice_probability(-3.0)
    mid = choice_probability(0.0)
    hi = choice_probability(3.0)
    assert lo < mid < hi
    assert 0 < lo and hi < 1


def test_budget_tier_gating():
    c = _cust({"inventory_advanced": 0.9}, budget=50_000)
    offer = Offer("a", "A", {"inventory_advanced"}, 0.7, 0.5,
                  [499, 1999, 5999, 49999], 0.8)
    util, tier = evaluate_offer(c, offer, FTIERS)
    assert tier == 2, "advanced needs should gate to Scale tier"


def test_enterprise_price_negotiates_toward_budget():
    c = _cust({"api_access": 0.9, "security_sso": 0.85, "sla_support": 0.9},
              budget=30_000)
    offer = Offer("a", "A", {"api_access", "security_sso", "sla_support"}, 0.7, 0.5,
                  [499, 1999, 5999, 49999], 0.8)
    _, tier = evaluate_offer(c, offer, FTIERS)
    assert tier == 3
