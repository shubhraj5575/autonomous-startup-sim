"""Customer agents: heterogeneous SMB buyers with needs, budgets, satisfaction
and churn dynamics. Purchase decisions use a logit discrete-choice model over
the company and its competitors, so competition and price elasticity emerge
from mechanics rather than being scripted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .rng import clamp

STATE_DORMANT = "dormant"      # not in market
STATE_SHOPPING = "shopping"    # actively evaluating (a "lead")
STATE_TRIAL = "trial"
STATE_ACTIVE = "active"
STATE_CHURNED = "churned"


@dataclass
class Offer:
    """What a vendor currently offers the market."""
    vendor_id: str                 # "us" or competitor id
    name: str
    features: set                  # feature ids owned
    quality: float                 # 0..1
    brand: float                   # 0..1 awareness/reputation
    tier_prices: list              # monthly INR per tier index
    support_quality: float         # 0..1


@dataclass(slots=True)
class Customer:
    cid: int
    segment: str
    budget: float                  # monthly INR willingness to pay
    needs: dict                    # feature_id -> weight (0..1)
    state: str = STATE_DORMANT
    awareness: float = 0.0         # 0..1, decays over time
    source: str = ""               # acquisition channel / "organic" / "referral"
    satisfaction: float = 0.55     # 0..1 while active
    vendor: str = ""               # vendor id if trial/active
    tier: int = 0
    monthly_fee: float = 0.0
    start_day: int = -1
    last_eval_day: int = -1
    shopping_since: int = -1
    trial_end_day: int = -1
    renewal_due_day: int = -1
    cooldown_until: int = -1       # after failed evaluation, don't re-shop for a while
    total_paid: float = 0.0
    months_paid: int = 0
    churn_prob_est: float = 0.0    # latest computed hazard (for analytics)
    incidents_experienced: int = 0


def fit_score(cust: Customer, features: set) -> float:
    """Weighted fraction of this customer's needs covered by the feature set."""
    tot = sum(cust.needs.values())
    if tot <= 0:
        return 0.5
    cov = sum(w for f, w in cust.needs.items() if f in features)
    return cov / tot


def min_required_tier(cust: Customer, feature_tiers: dict, n_tiers: int) -> int:
    t = 0
    for f, w in cust.needs.items():
        if w >= 0.5:
            t = max(t, feature_tiers.get(f, 0))
    return min(t, n_tiers - 1)


def evaluate_offer(cust: Customer, offer: Offer, feature_tiers: dict,
                   price_mult: float = 1.0, lam: float = 1.2,
                   challenger_penalty: float = 0.0) -> tuple[float, int]:
    """Logit-style utility of an offer for this customer.

    Returns (utility, chosen_tier). Price enters relative to budget; value is
    fit x quality x brand x support. Higher is better; the outside option is
    handled by the caller. challenger_penalty models incumbent trust/switching
    inertia against an unproven new vendor.
    """
    fitv = fit_score(cust, offer.features)
    qf = 0.35 + 0.65 * offer.quality
    bf = 1.0 + 1.0 * offer.brand
    sf = 0.88 + 0.18 * offer.support_quality
    value = max(1e-6, fitv * qf * bf * sf)

    tier = min_required_tier(cust, feature_tiers, len(offer.tier_prices))
    price = offer.tier_prices[tier] * price_mult
    # enterprise deals are negotiable toward budget but never below 60%
    if tier == len(offer.tier_prices) - 1:
        price = max(price * price_mult, min(price, cust.budget * 1.05))

    ratio = clamp(price / max(cust.budget, 50.0), 0.02, 12.0)
    util = math.log(value) - lam * math.log(ratio) - challenger_penalty
    return util, tier


def choice_probability(util: float, outside: float = -2.2, scale: float = 1.4) -> float:
    """P(customer picks vendor) vs staying put (outside option)."""
    return 1.0 / (1.0 + math.exp(-scale * (util - outside)))


class CustomerPool:
    def __init__(self, cfg, rng):
        self.rng = rng.stream("customers")
        self.cfg = cfg
        self.customers: list[Customer] = []
        self._by_state: dict[str, set[int]] = {s: set() for s in
                                               (STATE_DORMANT, STATE_SHOPPING, STATE_TRIAL,
                                                STATE_ACTIVE, STATE_CHURNED)}
        self._seg_state: dict[tuple, set] = {}
        self._build(cfg)

    def _make_customer(self, seg: str, spec: dict, cid: int) -> Customer:
        r = self.rng
        budget = max(spec["budget_min"], r.gauss(spec["budget_mean"], spec["budget_sd"]))
        needs = {}
        for f, w in spec["needs"].items():
            wn = clamp(w + r.gauss(0, 0.12), 0.15, 1.0)
            needs[f] = wn
        c = Customer(cid=cid, segment=seg, budget=budget, needs=needs)
        c.awareness = clamp(r.random() * 0.06, 0, 1)
        return c

    def _build(self, cfg):
        from .config import SEGMENTS
        cid = 0
        for seg, spec in SEGMENTS.items():
            for _ in range(spec["pool"]):
                c = self._make_customer(seg, spec, cid)
                self.customers.append(c)
                self._by_state[c.state].add(cid)
                self._seg_state.setdefault((seg, c.state), set()).add(cid)
                cid += 1

    def birth_customers(self, count: float) -> int:
        """Market expansion: new businesses enter the economy over time."""
        if count < 1:
            return 0
        from .config import SEGMENTS
        n = int(count)
        made = 0
        cid = len(self.customers)
        segs = list(SEGMENTS.keys())
        weights = [SEGMENTS[s]["pool"] for s in segs]
        for _ in range(n):
            # weighted pick without building full lists
            pick = self.rng.choices(segs, weights=weights, k=1)[0]
            c = self._make_customer(pick, SEGMENTS[pick], cid)
            self.customers.append(c)
            self._by_state[c.state].add(cid)
            self._seg_state.setdefault((pick, c.state), set()).add(cid)
            cid += 1
            made += 1
        return made

    @property
    def total_size(self) -> int:
        return len(self.customers)

    def seg_bucket(self, seg: str, state: str) -> set:
        return self._seg_state.get((seg, state), set())

    # -------------------------------------------------------------- helpers -
    def ids_in_state(self, state: str) -> set[int]:
        return self._by_state[state]

    def get(self, cid: int) -> Customer:
        return self.customers[cid]

    def transition(self, c: Customer, new_state: str) -> None:
        self._by_state[c.state].discard(c.cid)
        c.state = new_state
        self._by_state[new_state].add(c.cid)
        key_old = (c.segment, new_state)
        # maintain per-(segment,state) buckets
        for st in (STATE_DORMANT, STATE_SHOPPING, STATE_TRIAL, STATE_ACTIVE, STATE_CHURNED):
            self._seg_state.setdefault((c.segment, st), set()).discard(c.cid)
        self._seg_state.setdefault(key_old, set()).add(c.cid)

    def counts(self) -> dict:
        return {s: len(v) for s, v in self._by_state.items()}
